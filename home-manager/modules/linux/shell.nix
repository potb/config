{
  pkgs,
  lib,
  ...
}: let
  notifySend = "${pkgs.libnotify}/bin/notify-send";
  systemctlBin = "${pkgs.systemd}/bin/systemctl";
  bash = "${pkgs.bash}/bin/bash";
  rm = "${pkgs.coreutils}/bin/rm";
in {
  programs.zsh.initContent = lib.mkAfter ''
        unalias l

        remind() {
          if [[ $# -lt 2 ]]; then
            echo "Usage: remind <time> <message>"
            echo ""
            echo "  Duration:  remind 5m buy milk"
            echo "             remind 1h30m check oven"
            echo "             remind 90s quick test"
            echo "             remind in 5 minutes take a break"
            echo "             remind 30 water plants        (bare number = minutes)"
            echo ""
            echo "  Clock:     remind 14h30 standup meeting"
            echo "             remind 9:00 morning routine"
            echo ""
            echo "  List:      reminders"
            echo "  Cancel:    unremind <name>    or    unremind all"
            return 1
          fi

          local -a args=("$@")
          local idx=1

          # Strip leading "in"
          if [[ "''${(L)args[$idx]}" == "in" ]]; then
            (( idx++ ))
          fi

          local time_str="''${args[$idx]}"
          local msg_start=$(( idx + 1 ))

          # Bare number + optional unit word: "5 minutes" -> "5m", "5" -> "5m"
          if [[ "$time_str" =~ ^[0-9]+$ ]] && (( msg_start <= $# )); then
            local next="''${(L)args[$msg_start]}"
            case "$next" in
              s|sec|second|seconds)             time_str="''${time_str}s";   (( msg_start++ )) ;;
              m|min|mins|minute|minutes)        time_str="''${time_str}m";   (( msg_start++ )) ;;
              h|hr|hrs|hour|hours)              time_str="''${time_str}h";   (( msg_start++ )) ;;
              d|day|days)                       time_str="''${time_str}d";   (( msg_start++ )) ;;
              *)                               time_str="''${time_str}m"    ;;
            esac
          elif [[ "$time_str" =~ ^[0-9]+$ ]]; then
            time_str="''${time_str}m"
          fi

          # Remaining args = message
          local message="''${(j: :)args[$msg_start,$#]}"
          if [[ -z "$message" ]]; then
            echo "Error: no message provided"
            return 1
          fi

          local duration=""
          local fire_at=""
          local fire_epoch=""

          # Absolute time: NNhNN or NN:NN (24h clock, no trailing unit suffix)
          if [[ "$time_str" =~ ^([0-9]{1,2})[h:]([0-9]{1,2})$ ]]; then
            local target_h="''${match[1]}"
            local target_m="''${match[2]}"

            if (( target_h > 23 || target_m > 59 )); then
              echo "Error: invalid time ''${target_h}:''${target_m}"
              return 1
            fi

            local now_epoch=$(date +%s)
            local today=$(date +%Y-%m-%d)
            local target_epoch=$(date -d "$today $(printf '%02d:%02d:00' $target_h $target_m)" +%s)

            if (( target_epoch <= now_epoch )); then
              target_epoch=$(( target_epoch + 86400 ))
              fire_at="tomorrow $(printf '%02d:%02d' $target_h $target_m)"
            else
              fire_at="today $(printf '%02d:%02d' $target_h $target_m)"
            fi

            local delta=$(( target_epoch - now_epoch ))
            duration="''${delta}s"
            fire_epoch=$target_epoch

            # Human-readable delta for display
            local dh=$(( delta / 3600 ))
            local dm=$(( (delta % 3600) / 60 ))
            local human_delta=""
            (( dh > 0 )) && human_delta="''${dh}h"
            (( dm > 0 )) && human_delta="''${human_delta}''${dm}m"
            [[ -z "$human_delta" ]] && human_delta="<1m"
            fire_at="$fire_at, in $human_delta"
          else
            # Relative duration — validate with systemd-analyze
            duration="$time_str"

            local parsed
            parsed=$(systemd-analyze timespan "$duration" 2>/dev/null)
            if [[ $? -ne 0 ]]; then
              echo "Error: invalid duration '$duration'"
              echo "Examples: 5m, 1h30m, 90s, 2h, 1d"
              return 1
            fi

            # Extract microseconds, convert to seconds for absolute fire time
            local usecs=$(echo "$parsed" | command grep -oP '(?<=μs: )\d+')
            if [[ -n "$usecs" ]] && (( usecs > 0 )); then
              local total_secs=$(( usecs / 1000000 ))
              fire_epoch=$(( $(date +%s) + total_secs ))
              fire_at="at $(date -d "@$fire_epoch" '+%H:%M')"
            fi
          fi

          if [[ -z "$fire_epoch" ]]; then
            echo "Error: could not calculate fire time"
            return 1
          fi

          local fire_cal=$(date -d "@$fire_epoch" '+%Y-%m-%d %H:%M:%S')
          local unit_name="remind-$(date +%s)-$RANDOM"
          local unit_dir="$HOME/.config/systemd/user"
          local script_dir="$HOME/.local/share/reminders"
          mkdir -p "$unit_dir" "$script_dir"

          # Sanitize message for systemd unit Description (escape % specifiers, strip newlines)
          local safe_desc="''${message//$'\n'/ }"
          safe_desc="''${safe_desc//\%/%%}"

          # Write fire-and-cleanup script with full Nix store paths (systemd services have minimal PATH)
          local escaped_msg=$(printf '%q' "$message")
          local script_path="$script_dir/$unit_name.sh"
          {
            echo "#!${bash}"
            echo "${notifySend} -u critical -a Reminder Reminder $escaped_msg"
            echo "${systemctlBin} --user disable --now $unit_name.timer 2>/dev/null || true"
            echo "${rm} -f \"$unit_dir/$unit_name.timer\" \"$unit_dir/$unit_name.service\" \"$script_path\""
            echo "${systemctlBin} --user daemon-reload 2>/dev/null || true"
          } > "$script_path"
          chmod +x "$script_path"

          # Write systemd service unit
          cat > "$unit_dir/$unit_name.service" <<REMINDUNIT
    [Unit]
    Description=$safe_desc

    [Service]
    Type=oneshot
    ExecStart=$script_path
    REMINDUNIT

          # Write systemd timer unit (Persistent=true survives reboots)
          cat > "$unit_dir/$unit_name.timer" <<REMINDUNIT
    [Unit]
    Description=Reminder: $safe_desc

    [Timer]
    OnCalendar=$fire_cal
    Persistent=true
    Unit=$unit_name.service

    [Install]
    WantedBy=timers.target
    REMINDUNIT

          systemctl --user daemon-reload
          systemctl --user enable --now "$unit_name.timer" 2>&1 \
            | command grep -v "^Created"

          if (( pipestatus[1] == 0 )); then
            echo "remind: \"$message\" ($duration''${fire_at:+, $fire_at})"
          else
            echo "Error: failed to create reminder"
            rm -f "$unit_dir/$unit_name.timer" "$unit_dir/$unit_name.service" "$script_path"
            return 1
          fi
        }

        reminders() {
          local units
          units=($(systemctl --user list-units --type=timer --plain --no-legend 'remind-*' 2>/dev/null | awk '{print $1}'))

          if [[ ''${#units[@]} -eq 0 ]]; then
            echo "No active reminders"
            return 0
          fi

          for timer in "''${units[@]}"; do
            local svc="''${timer%.timer}.service"
            local desc=$(systemctl --user show "$svc" -p Description --value 2>/dev/null)
            local next_raw=$(systemctl --user show "$timer" -p NextElapseUSecRealtime --value 2>/dev/null)

            local next_fmt=""
            if [[ -n "$next_raw" && "$next_raw" != "n/a" ]]; then
              next_fmt=$(date -d "$next_raw" '+%a %H:%M' 2>/dev/null)
            fi

            printf "  %-40s %-12s [%s]\n" "\"''${desc:-?}\"" "''${next_fmt:+at $next_fmt}" "''${timer%.timer}"
          done
        }

        unremind() {
          if [[ $# -lt 1 ]]; then
            reminders
            echo ""
            echo "Usage: unremind <name>   (copy from list above)"
            echo "       unremind all      (cancel all reminders)"
            return 1
          fi

          local script_dir="$HOME/.local/share/reminders"
          local unit_dir="$HOME/.config/systemd/user"

          if [[ "$1" == "all" ]]; then
            local units
            units=($(systemctl --user list-units --type=timer --plain --no-legend 'remind-*' 2>/dev/null | awk '{print $1}'))

            if [[ ''${#units[@]} -eq 0 ]]; then
              echo "No active reminders"
              return 0
            fi

            for timer in "''${units[@]}"; do
              local unit="''${timer%.timer}"
              systemctl --user disable --now "$timer" 2>/dev/null
              systemctl --user stop "$unit.service" 2>/dev/null
              rm -f "$unit_dir/$unit.timer" "$unit_dir/$unit.service" "$script_dir/$unit.sh"
              echo "Cancelled: $unit"
            done
            systemctl --user daemon-reload 2>/dev/null
            return 0
          fi

          local unit="$1"
          unit="''${unit%.timer}"
          unit="''${unit%.service}"
          systemctl --user disable --now "''${unit}.timer" 2>/dev/null
          systemctl --user stop "''${unit}.service" 2>/dev/null
          rm -f "$unit_dir/$unit.timer" "$unit_dir/$unit.service" "$script_dir/$unit.sh"
          systemctl --user daemon-reload 2>/dev/null
          echo "Cancelled: $unit"
        }
  '';
}
