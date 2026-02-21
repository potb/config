{
  pkgs,
  lib,
  ...
}: let
  notifySend = "${pkgs.libnotify}/bin/notify-send";
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

        # Human-readable delta for display
        local dh=$(( delta / 3600 ))
        local dm=$(( (delta % 3600) / 60 ))
        local human_delta=""
        (( dh > 0 )) && human_delta="''${dh}h"
        (( dm > 0 )) && human_delta="''${human_delta}''${dm}m"
        [[ -z "$human_delta" ]] && human_delta="<1m"
        fire_at="$fire_at, in $human_delta"
      else
        # Relative duration — pass to systemd as-is
        duration="$time_str"

        # Validate and parse with systemd-analyze (the actual parser)
        local parsed
        parsed=$(systemd-analyze timespan "$duration" 2>/dev/null)
        if [[ $? -ne 0 ]]; then
          echo "Error: invalid duration '$duration'"
          echo "Examples: 5m, 1h30m, 90s, 2h, 1d"
          return 1
        fi

        # Extract microseconds from systemd-analyze output, convert to seconds
        local usecs=$(echo "$parsed" | command grep -oP '(?<=μs: )\d+')
        if [[ -n "$usecs" ]] && (( usecs > 0 )); then
          local total_secs=$(( usecs / 1000000 ))
          fire_at="at $(date -d "+''${total_secs} seconds" '+%H:%M')"
        fi
      fi

      local unit_name="remind-$(date +%s)-$RANDOM"

      systemd-run --user \
        --unit="$unit_name" \
        --description="$message" \
        --on-active="$duration" \
        --timer-property=AccuracySec=1s \
        -- ${notifySend} -u critical -a "Reminder" "Reminder" "$message" 2>&1 \
        | command grep -v "^Running"

      if (( pipestatus[1] == 0 )); then
        echo "remind: \"$message\" ($duration''${fire_at:+, $fire_at})"
      else
        echo "Error: failed to create reminder"
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

      if [[ "$1" == "all" ]]; then
        local units
        units=($(systemctl --user list-units --type=timer --plain --no-legend 'remind-*' 2>/dev/null | awk '{print $1}'))

        if [[ ''${#units[@]} -eq 0 ]]; then
          echo "No active reminders"
          return 0
        fi

        for timer in "''${units[@]}"; do
          systemctl --user stop "$timer" 2>/dev/null
          echo "Cancelled: ''${timer%.timer}"
        done
        return 0
      fi

      local unit="$1"
      unit="''${unit%.timer}"
      unit="''${unit%.service}"
      systemctl --user stop "''${unit}.timer" 2>/dev/null
      systemctl --user stop "''${unit}.service" 2>/dev/null
      echo "Cancelled: $unit"
    }
  '';
}
