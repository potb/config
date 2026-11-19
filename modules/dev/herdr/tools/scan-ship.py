"""scan-ship: GitHub PRs through gh and Linear dependencies. Read-only. Contract: tools/CONTRACT.md output 3."""
import calendar
import fnmatch
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

H = os.path.expanduser("~/.config/herdr-app")
REPO = "BeCosto/beakon"
REPO_DIR = os.path.expanduser("~/projects/costo/beakon")
LINEAR_URL = "https://api.linear.app/graphql"
SHIP = os.path.join(H, "data", "ship-core")
LIN = os.path.join(H, "data", "linear")
WF = os.path.join(H, "data", "wf-core")
DEFAULT_CFG = {"projects": ["Effect adoption"],
               "satisfied": ["Done", "Canceled", "Duplicate", "On Staging"],
               "staleHours": 12, "team": "TECH"}
ACTIVE = ("Implementing", "In Review", "Needs Human")
KEY = ""
NOW = time.time()
ERRORS = []


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def scrub(s):
    s = str(s)
    return s.replace(KEY, "***") if KEY else s


def iso_ms(s):
    if not s:
        return 0
    try:
        t = time.strptime(s.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")
        return calendar.timegm(t) * 1000
    except ValueError:
        return 0


def head_has(ident, head):
    pat = r"(?<![A-Za-z0-9])" + re.escape(ident) + r"(?![0-9])"
    return re.search(pat, head, re.I) is not None


def hours(ms):
    return round(max(0, NOW * 1000 - ms) / 3600000, 1) if ms else 0


def gh(args, timeout=60):
    p = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("gh " + " ".join(args[:3]) + ": " + (p.stderr.strip().splitlines() or ["failed"])[-1])
    return p.stdout


def load_config():
    path = os.path.join(LIN, "config.json")
    cfg = read_json(path)
    if cfg is None:
        write_json(path, DEFAULT_CFG)
        cfg = {}
    out = dict(DEFAULT_CFG)
    out.update({k: v for k, v in cfg.items() if k in DEFAULT_CFG})
    return out


def rulesets():
    path = os.path.join(SHIP, "rulesets.json")
    c = read_json(path)
    if c and NOW - c.get("ts", 0) < 86400 and c.get("rules") is not None:
        return c
    rules = []
    for r in json.loads(gh(["api", "repos/%s/rulesets" % REPO])):
        if r.get("enforcement") != "active" or r.get("target") != "branch":
            continue
        d = json.loads(gh(["api", "repos/%s/rulesets/%s" % (REPO, r["id"])]))
        ctx = []
        for rule in d.get("rules", []):
            if rule.get("type") == "required_status_checks":
                ctx += [x["context"] for x in rule["parameters"].get("required_status_checks", [])]
        rn = (d.get("conditions") or {}).get("ref_name") or {}
        rules.append({"name": d["name"], "include": rn.get("include", []),
                      "exclude": rn.get("exclude", []), "contexts": ctx})
    default = json.loads(gh(["api", "repos/" + REPO, "--jq", "{d: .default_branch}"]))["d"]
    c = {"ts": NOW, "default": default, "rules": rules}
    write_json(path, c)
    return c


def ref_match(patterns, ref, default):
    for p in patterns:
        if p == "~ALL":
            return True
        if p == "~DEFAULT_BRANCH":
            if ref == "refs/heads/" + default:
                return True
            continue
        if fnmatch.fnmatchcase(ref, p.replace("**", "*")):
            return True
    return False


def required_for(base, rs):
    ref = "refs/heads/" + base
    names = []
    for r in rs["rules"]:
        if r["contexts"] and ref_match(r["include"], ref, rs["default"]) and not ref_match(r["exclude"], ref, rs["default"]):
            names += [c for c in r["contexts"] if c not in names]
    return names


PR_QUERY = """query($after:String){ viewer{login} repository(owner:"BeCosto",name:"beakon"){
 pullRequests(states:OPEN,first:50,after:$after){ pageInfo{hasNextPage endCursor} nodes{
 number title url isDraft author{login} baseRefName headRefName createdAt updatedAt mergeStateStatus mergeable
 autoMergeRequest{enabledAt}
 commits(last:1){nodes{commit{oid statusCheckRollup{contexts(first:100){pageInfo{hasNextPage} nodes{__typename
  ... on CheckRun{name status conclusion startedAt completedAt checkSuite{workflowRun{databaseId}}}
  ... on StatusContext{context state createdAt}}}}}}}} } } }"""


def fetch_prs():
    out, after = [], None
    while True:
        args = ["api", "graphql", "-f", "query=" + PR_QUERY]
        if after:
            args += ["-F", "after=" + after]
        d = json.loads(gh(args))
        if d.get("errors"):
            raise RuntimeError("graphql: " + str(d["errors"][0].get("message")))
        viewer = (d["data"].get("viewer") or {}).get("login")
        p = d["data"]["repository"]["pullRequests"]
        for n in p["nodes"]:
            n["mine"] = bool(viewer) and (n.get("author") or {}).get("login") == viewer
        out += p["nodes"]
        if not p["pageInfo"]["hasNextPage"]:
            return out
        after = p["pageInfo"]["endCursor"]


def worktrees():
    m = {}
    try:
        p = subprocess.run(["git", "-C", REPO_DIR, "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return m
    path = None
    for line in p.stdout.splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line.startswith("branch refs/heads/") and path:
            m.setdefault(line[18:], path)
    return m


TICKET = re.compile(r"[A-Za-z]+-\d+")


def ticket_of(*texts):
    for t in texts:
        m = TICKET.search(t or "")
        if m:
            return m.group(0).upper()
    return None


def last_check_activity(nodes):
    stamps = [iso_ms(n.get("completedAt") or n.get("startedAt") or n.get("createdAt")) for n in nodes]
    return max([s for s in stamps if s] or [0])


def check_states(nodes, required, draft):
    latest = {}
    for n in nodes:
        if n["__typename"] == "CheckRun":
            name, ts = n["name"], iso_ms(n.get("startedAt"))
            if n["status"] != "COMPLETED":
                st = "pending"
            else:
                c = n.get("conclusion") or ""
                st = ("pass" if c in ("SUCCESS", "SKIPPED", "NEUTRAL") else
                      "cancelled" if c == "CANCELLED" else
                      "pending" if c in ("STALE", "") else "fail")
            run = ((n.get("checkSuite") or {}).get("workflowRun") or {}).get("databaseId")
        else:
            name, ts, run = n["context"], iso_ms(n.get("createdAt")), None
            s = n["state"]
            st = "pass" if s == "SUCCESS" else "pending" if s in ("PENDING", "EXPECTED") else "fail"
        if name in required and (name not in latest or ts >= latest[name][1]):
            latest[name] = (st, ts, run)
    tally = {"pass": 0, "fail": 0, "pending": 0, "cancelled": 0}
    failed_runs, pending_start = [], 0
    for name in required:
        if name not in latest:
            if not draft:
                tally["pending"] += 1
            continue
        st, ts, run = latest[name]
        tally[st] += 1
        if st == "fail" and run:
            failed_runs.append(run)
        if st == "pending" and ts and (not pending_start or ts < pending_start):
            pending_start = ts
    return tally, failed_runs, pending_start, [n for n in required if n in latest and latest[n][0] == "fail"]


def load_owners():
    state = read_json(os.path.join(WF, "state.json")) or {}
    term = {r.get("runId"): r.get("terminal") or "" for r in state.get("runs", [])}
    files = glob.glob(os.path.join(WF, "runs", "*.json"))
    return term, files


def owner_for(ticket, term, files, cache):
    if not ticket or not files:
        return None
    best = None
    for f in files:
        if f not in cache:
            try:
                raw = open(f).read()
            except OSError:
                cache[f] = (set(), None)
                continue
            cache[f] = ({t.upper() for t in TICKET.findall(raw)}, raw)
        found, raw = cache[f]
        if ticket not in found or raw is None:
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        for a in d.get("agents", []):
            if a.get("ticket") == ticket or head_has(ticket, a.get("label") or ""):
                rank = (a.get("state") in ("running", "stuck"), a.get("lastAt") or 0)
                if best is None or rank > best[0]:
                    best = (rank, {"terminal": term.get(d.get("runId"), ""), "runId": d.get("runId", "")})
    return best[1] if best else None


def scan_prs(rs, owners):
    raw = fetch_prs()
    wt = worktrees()
    heads = {p["headRefName"] for p in raw}
    term, files = owners
    cache = {}
    prs = []
    for p in raw:
        commit = p["commits"]["nodes"][0]["commit"] if p["commits"]["nodes"] else {}
        roll = commit.get("statusCheckRollup") or {"contexts": {"nodes": [], "pageInfo": {}}}
        if roll["contexts"]["pageInfo"].get("hasNextPage"):
            ERRORS.append("PR %d: more than 100 checks, tally may be incomplete" % p["number"])
        required = required_for(p["baseRefName"], rs) if p["baseRefName"] not in heads else []
        tally, failed_runs, pstart, failed_names = check_states(
            roll["contexts"]["nodes"], required, p["isDraft"])
        created, updated = iso_ms(p["createdAt"]), iso_ms(p["updatedAt"])
        idle = hours(max(updated or 0, last_check_activity(roll["contexts"]["nodes"])))
        ci_running = (NOW * 1000 - pstart) / 60000 if pstart else None
        ms, mg = p["mergeStateStatus"], p["mergeable"]
        reason, detail = None, ""
        if ms == "DIRTY" or mg == "CONFLICTING":
            reason, detail = "conflict", "Merge conflicts with " + p["baseRefName"]
        elif tally["fail"]:
            reason, detail = "red", "Required failed: " + ", ".join(failed_names)
        elif ms == "BLOCKED" and tally["cancelled"]:
            reason, detail = "cancelled-required", "%d required check(s) cancelled, no newer run" % tally["cancelled"]
        elif pstart and (NOW * 1000 - pstart) > 20 * 60000:
            reason, detail = "pending-long", "Required check pending for %d min" % ((NOW * 1000 - pstart) // 60000)
        elif p["baseRefName"] in heads:
            reason, detail = "stack-waiting", "Base %s is another open PR" % p["baseRefName"]
        elif not p["isDraft"] and ms == "CLEAN" and idle > 1:
            reason, detail = "ready-unmerged", "Clean and ready, idle %.0f h" % idle
        elif p["isDraft"] and idle > 24:
            reason, detail = "draft-forgotten", "Draft idle %.0f h" % idle
        elif ms in ("BLOCKED", "UNSTABLE", "BEHIND", "UNKNOWN", "HAS_HOOKS"):
            detail = {"BLOCKED": "Blocked with every required check green%s" % (", auto-merge on" if p.get("autoMergeRequest") else ""),
                      "UNSTABLE": "Only non-required checks failing",
                      "BEHIND": "Behind " + p["baseRefName"],
                      "UNKNOWN": "GitHub has not computed mergeability yet"}.get(ms, ms)
        t = ticket_of(p["headRefName"], p["title"])
        prs.append({"number": p["number"], "title": p["title"], "url": p["url"], "isDraft": p["isDraft"],
                    "author": (p.get("author") or {}).get("login"), "mine": p.get("mine", False),
                    "base": p["baseRefName"], "head": p["headRefName"], "ticket": t,
                    "ageH": hours(created), "idleH": idle, "ciRunningMin": ci_running, "mergeState": ms, "mergeable": mg,
                    "autoMerge": bool(p.get("autoMergeRequest")), "required": tally,
                    "reason": reason, "reasonDetail": detail, "failedRunIds": failed_runs,
                    "worktree": wt.get(p["headRefName"]),
                    "owner": owner_for(t, term, files, cache)})
    prs.sort(key=lambda x: x["number"])
    return prs


def linear(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(LINEAR_URL, body, {"Authorization": KEY, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=40)
    except urllib.error.HTTPError as e:
        r = e
    try:
        d = json.load(r)
    except ValueError:
        raise RuntimeError("linear: HTTP %s, non-JSON body" % getattr(r, "status", "?"))
    if d.get("errors"):
        raise RuntimeError("linear: " + scrub(d["errors"][0].get("message", "error"))[:200])
    return d["data"]


PROJECTS_Q = "query($a:String){projects(first:100,after:$a){pageInfo{hasNextPage endCursor} nodes{id name slugId url}}}"
ISSUES_Q = """query($id:String!,$a:String){project(id:$id){issues(first:50,after:$a){
 pageInfo{hasNextPage endCursor} nodes{identifier title url updatedAt state{name type}
 attachments(first:10){nodes{url}}
 inverseRelations(first:25){pageInfo{hasNextPage endCursor} nodes{type issue{identifier title url updatedAt state{name}}}}}}}}"""
MORE_Q = """query($id:String!,$a:String){issue(id:$id){inverseRelations(first:50,after:$a){
 pageInfo{hasNextPage endCursor} nodes{type issue{identifier title url updatedAt state{name}}}}}}"""


PR_LINKS_Q = '{ pullRequests(first:100, filter:{status:{nin:["merged","closed"]}}){ nodes{ url appUrl } } }'
MY_TICKETS_Q = """query($a:String){ viewer{ assignedIssues(first:100, after:$a,
 filter:{state:{type:{nin:["completed","canceled"]}}}){
 pageInfo{hasNextPage endCursor} nodes{identifier title url}}}}"""


def my_tickets():
    path = os.path.join(SHIP, "my-tickets.json")
    cached = read_json(path, {}) or {}
    if not KEY:
        return cached
    try:
        out, after = {}, None
        while True:
            d = linear(MY_TICKETS_Q, {"a": after})["viewer"]["assignedIssues"]
            for n in d["nodes"]:
                out[n["identifier"].upper()] = {"title": n["title"], "url": n["url"]}
            if not d["pageInfo"]["hasNextPage"]:
                break
            after = d["pageInfo"]["endCursor"]
        write_json(path, out)
        return out
    except (RuntimeError, urllib.error.URLError, TimeoutError, KeyError, TypeError) as e:
        ERRORS.append(scrub(str(e))[:200])
        return cached


def attach_linear_links(prs):
    path = os.path.join(SHIP, "pr-links.json")
    links = read_json(path, {}) or {}
    try:
        fresh = {n["url"]: n["appUrl"] for n in linear(PR_LINKS_Q)["pullRequests"]["nodes"] if n.get("appUrl")}
        links = fresh
        write_json(path, links)
    except (RuntimeError, urllib.error.URLError, TimeoutError, KeyError, TypeError) as e:
        ERRORS.append(scrub(str(e))[:200])
    for p in prs:
        p["linearUrl"] = links.get(p["url"])


def resolve_projects(names):
    allp, after = [], None
    while True:
        d = linear(PROJECTS_Q, {"a": after})["projects"]
        allp += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            break
        after = d["pageInfo"]["endCursor"]
    out = []
    for want in names:
        w = want.strip().lower()
        hit = next((p for p in allp if w in (p["name"].lower(), p["slugId"].lower(), p["id"].lower())
                    or p["url"].lower().rstrip("/").endswith(w)), None)
        if hit:
            out.append(hit)
        else:
            ERRORS.append("Linear project not found: " + want)
    return out


def fetch_issues(pid):
    out, after = [], None
    while True:
        d = linear(ISSUES_Q, {"id": pid, "a": after})["project"]["issues"]
        for n in d["nodes"]:
            rel = n["inverseRelations"]
            nodes = list(rel["nodes"])
            cur = rel["pageInfo"]
            while cur.get("hasNextPage"):
                m = linear(MORE_Q, {"id": n["identifier"], "a": cur["endCursor"]})["issue"]["inverseRelations"]
                nodes += m["nodes"]
                cur = m["pageInfo"]
            n["rels"] = nodes
            out.append(n)
        if not d["pageInfo"]["hasNextPage"]:
            return out
        after = d["pageInfo"]["endCursor"]


def scan_project(proj, cfg, prs, term, files):
    issues = fetch_issues(proj["id"])
    satisfied = set(cfg["satisfied"])
    by_id = {i["identifier"]: i for i in issues}
    blockers, blocks, ext = {}, {}, {}
    for i in issues:
        ids = []
        for r in i["rels"]:
            if r["type"] != "blocks":
                continue
            b = r["issue"]
            ids.append(b["identifier"])
            ext[b["identifier"]] = b
            blocks.setdefault(b["identifier"], []).append(i["identifier"])
        blockers[i["identifier"]] = ids
    state_of = {k: v["state"]["name"] for k, v in by_id.items()}
    for k, v in ext.items():
        state_of.setdefault(k, v["state"]["name"])
    open_heads = [(p["head"].lower(), p["number"]) for p in prs]
    cache = {}

    def issue_obj(ident):
        src = by_id.get(ident)
        if src:
            title, url, upd = src["title"], src["url"], iso_ms(src["updatedAt"])
            att = [a["url"] for a in src["attachments"]["nodes"] if "github.com/BeCosto/beakon/pull" in a["url"]]
        else:
            e = ext[ident]
            title, url, upd, att = e["title"], e["url"], iso_ms(e.get("updatedAt")), []
        pr = next((n for h, n in open_heads if head_has(ident, h)), None)
        if pr is None and att:
            m = re.search(r"/pull/(\d+)", att[0])
            pr = int(m.group(1)) if m else None
        return {"identifier": ident, "title": title, "url": url, "state": state_of[ident],
                "updatedAt": upd, "staleH": hours(upd), "blockers": blockers.get(ident, []),
                "pr": pr, "owner": owner_for(ident, term, files, cache)}, bool(att)

    def transitive(ident):
        seen, stack = set(), list(blocks.get(ident, []))
        while stack:
            x = stack.pop()
            if x in seen or x == ident:
                continue
            seen.add(x)
            stack += blocks.get(x, [])
        return len([x for x in seen if state_of.get(x) not in satisfied])

    res = {"name": proj["name"], "url": proj["url"], "counts": {}, "startable": [],
           "rootBlockers": [], "noPr": [], "stale": [], "awaitingMain": []}
    roots = set()
    for i in issues:
        ident, st = i["identifier"], state_of[i["identifier"]]
        res["counts"][st] = res["counts"].get(st, 0) + 1
        o, has_att = issue_obj(ident)
        if st in ("Todo", "Backlog") and all(state_of[b] in satisfied for b in blockers[ident]):
            res["startable"].append(o)
        if st in ACTIVE:
            if not has_att and not any(head_has(ident, h) for h, _ in open_heads):
                res["noPr"].append(o)
            if (NOW * 1000 - o["updatedAt"]) > cfg["staleHours"] * 3600000:
                res["stale"].append(o)
        if st == "On Staging":
            res["awaitingMain"].append(o)
        for b in blockers[ident]:
            if state_of[b] not in satisfied and state_of[b] in ACTIVE:
                roots.add(b)
    for b in roots:
        res["rootBlockers"].append({"issue": issue_obj(b)[0], "blocksTransitively": transitive(b)})
    res["rootBlockers"].sort(key=lambda r: (-r["blocksTransitively"], r["issue"]["identifier"]))
    for key in ("startable", "noPr", "stale", "awaitingMain"):
        res[key].sort(key=lambda o: o["identifier"])
    return res


def scan_linear(cfg, prs, owners):
    term, files = owners
    out = []
    for p in resolve_projects(cfg["projects"]):
        try:
            out.append(scan_project(p, cfg, prs, term, files))
        except RuntimeError as e:
            ERRORS.append("Linear %s: %s" % (p["name"], e))
    return {"ts": int(NOW * 1000), "projects": out}


def tech_summary(lin):
    s = {"startable": 0, "rootBlockers": 0, "noPr": 0, "stale": 0, "awaitingMain": 0}
    for p in (lin or {}).get("projects", []):
        for k in s:
            s[k] += len(p[k])
    return s


def make_events(prs, lin):
    path = os.path.join(SHIP, "notified.json")
    old = read_json(path) or {}
    ev = []
    if "prs" in old:
        for p in prs:
            r = p["reason"]
            if r and old["prs"].get(str(p["number"])) != r:
                ev.append({"kind": "pr", "title": "PR #%d %s" % (p["number"], r),
                           "body": "%s: %s" % (p["title"], p["reasonDetail"]), "url": p["url"]})
    new = {"prs": {str(p["number"]): p["reason"] for p in prs if p["reason"]}}
    if lin is not None:
        cur = {}
        for pr in lin["projects"]:
            for k, label in (("stale", "stale"), ("noPr", "no PR")):
                for o in pr[k]:
                    key = "%s:%s" % (k, o["identifier"])
                    cur[key] = 1
                    if "tech" in old and key not in old["tech"]:
                        ev.append({"kind": "tech", "title": "%s %s" % (o["identifier"], label),
                                   "body": "%s (%s, %.0f h since update)" % (o["title"], o["state"], o["staleH"]),
                                   "url": o["url"]})
        new["tech"] = cur
    elif "tech" in old:
        new["tech"] = old["tech"]
    write_json(path, new)
    return ev


def main():
    global KEY
    with_linear = "--linear" in sys.argv[1:]
    cfg = load_config()
    rs = rulesets()
    owners = load_owners()
    all_prs = scan_prs(rs, owners)
    try:
        with open(os.path.join(LIN, "key")) as f:
            KEY = f.read().strip()
    except OSError:
        KEY = ""
    if KEY:
        attach_linear_links(all_prs)
    tickets = my_tickets()
    prs = [p for p in all_prs if p["mine"] or p["ticket"] in tickets]
    for p in prs:
        p["ticketTitle"] = (tickets.get(p["ticket"]) or {}).get("title")
        p["ticketUrl"] = (tickets.get(p["ticket"]) or {}).get("url")
    write_json(os.path.join(SHIP, "prs.json"), {"ts": int(NOW * 1000), "prs": prs})
    cnt = lambda r: sum(1 for p in prs if p["reason"] == r)
    prs_summary = {"open": len(prs), "stuck": sum(1 for p in prs if p["reason"]),
                   "conflict": cnt("conflict"), "red": cnt("red"),
                   "cancelledRequired": cnt("cancelled-required"), "pendingLong": cnt("pending-long"),
                   "readyUnmerged": cnt("ready-unmerged"), "draftForgotten": cnt("draft-forgotten"),
                   "stackWaiting": cnt("stack-waiting")}
    lin = read_json(os.path.join(SHIP, "linear.json"))
    fresh = None
    if with_linear:
        try:
            with open(os.path.join(LIN, "key")) as f:
                KEY = f.read().strip()
            fresh = scan_linear(cfg, all_prs, owners)
            lin = fresh
            write_json(os.path.join(SHIP, "linear.json"), fresh)
        except (OSError, RuntimeError, urllib.error.URLError, TimeoutError) as e:
            ERRORS.append(scrub(e)[:200])
    events = make_events(prs, fresh)
    return {"ok": True, "ts": int(NOW * 1000), "prs": prs_summary, "tech": tech_summary(lin),
            "events": events, "errors": ERRORS}


if __name__ == "__main__":
    try:
        out = main()
    except Exception as e:
        out = {"ok": False, "error": scrub(e)[:300]}
    print(json.dumps(out))
