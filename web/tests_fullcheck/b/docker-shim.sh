#!/bin/bash
# fake docker for status.ps1 tests. SHIM_MODE: full|partial|empty|badport ; SHIM_JSON: lines|array
a="$*"; M=${SHIM_MODE:-full}
echo "docker $a" >> ${SHIM_LOG:-/dev/null}
names="ytweb-db-1 ytweb-migrate-1 ytweb-api-1 ytweb-worker-1 ytweb-web-1"
[ "$M" = partial ] && names="ytweb-db-1 ytweb-api-1 ytweb-web-1"
[ "$M" = empty ] && names=""
case "$1" in
 info) echo "27.3.1|linux";;
 version) echo 27.3.1;;
 ps)
   if [ "$M" = psempty ]; then exit 0; fi
   if [[ "$a" == *"--format"* ]]; then
     for n in $names; do
       p=""; [ "$n" = ytweb-web-1 ] && p="127.0.0.1:8080->8080/tcp"
       [ "$M" = badport ] && [ "$n" = ytweb-api-1 ] && p="0.0.0.0:8000->8000/tcp, :::8000->8000/tcp"
       echo "$n|$p"
     done
   else for n in $names; do echo "id_$n"; done; fi;;
 inspect) echo "/${@: -1} user=app readOnly=true privileged=false capDrop=[ALL] security=[no-new-privileges] network=ytweb_default";;
 compose)
   shift
   if [ "$1" = version ]; then echo 2.29.7; exit 0; fi
   if [[ "$a" == *" exec -T api python -m ytweb.live_check"* ]]; then cd /home/user/youtube-subject-modify-auto/web/backend && exec /home/user/youtube-subject-modify-auto/.harness-tmp/be/bin/python -m ytweb.live_check; fi
   if [[ "$a" == *" port web 8080"* ]]; then [ "$M" = empty ] && exit 1; echo "127.0.0.1:8080"; exit 0; fi
   if [[ "$a" == *" ps -a --format json"* ]]; then
     rows=()
     for n in $names; do s=${n#ytweb-}; s=${s%-1}
       if [ $s = migrate ]; then rows+=("{\"Name\":\"$n\",\"Service\":\"$s\",\"State\":\"exited\",\"Health\":\"\",\"ExitCode\":0}")
       elif [ $s = worker ]; then rows+=("{\"Name\":\"$n\",\"Service\":\"$s\",\"State\":\"running\",\"Health\":\"healthy\",\"ExitCode\":0}")
       else rows+=("{\"Name\":\"$n\",\"Service\":\"$s\",\"State\":\"running\",\"Health\":\"healthy\",\"ExitCode\":0}"); fi; done
     if [ "${SHIM_JSON:-lines}" = array ]; then (IFS=,; echo "[${rows[*]}]"); else for r in "${rows[@]}"; do echo "$r"; done; fi
     exit 0
   fi
   echo "unhandled compose: $a" >&2; exit 0;;
 *) echo "unhandled: $a" >&2;;
esac
