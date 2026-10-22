#!@shell@
set -uo pipefail

helper_bin=@resources@/Release/wispr-flow-linux-helper
export PATH=@runtimePath@:$PATH

source @lib@/launcher-common.sh

_doctor_check_sandbox() {
	if unshare --user --map-root-user true 2>/dev/null; then
		_pass 'Chromium sandbox: unprivileged user namespaces available'
	else
		_fail 'Chromium sandbox: unprivileged user namespaces are disabled'
		_info 'The nixpkgs Electron ships no setuid chrome-sandbox and relies on them.'
	fi
}

_doctor_check_desktop_entry() {
	local dir entry='' handler
	for dir in ${XDG_DATA_DIRS//:/ }; do
		if [[ -f $dir/applications/wispr-flow.desktop ]]; then
			entry=$dir/applications/wispr-flow.desktop
			break
		fi
	done
	if [[ -n $entry ]]; then
		_pass "Desktop entry: $entry"
	else
		_warn 'Desktop entry: wispr-flow.desktop is not on XDG_DATA_DIRS'
	fi
	handler=$(@xdgMime@ query default x-scheme-handler/wispr-flow 2>/dev/null)
	if [[ $handler == wispr-flow.desktop ]]; then
		_pass 'Sign-in links: wispr-flow:// opens wispr-flow.desktop'
	else
		_fail "Sign-in links: wispr-flow:// opens '${handler:-nothing}'"
		_info 'The browser cannot hand the login back to the app.'
		_info 'Set x-scheme-handler/wispr-flow to wispr-flow.desktop in mimeapps.list.'
	fi
}

if [[ ${1:-} == --doctor ]]; then
	run_doctor "$helper_bin" @electronBinary@
	exit $?
fi

setup_logging || exit 1
cleanup_stale_lock
migrate_legacy_data_dir

log_message "--- Wispr Flow @version@ (nix) $(date) args: $* ---"
log_session_env

if ! check_display; then
	echo 'Wispr Flow needs a graphical session (Wayland or X11).' >&2
	echo 'Run "wispr-flow --doctor" to diagnose the setup.' >&2
	exit 1
fi

detect_display_backend
build_electron_args nix

exec @electronWrapper@ "${electron_args[@]}" "$@" >>"$log_file" 2>&1
