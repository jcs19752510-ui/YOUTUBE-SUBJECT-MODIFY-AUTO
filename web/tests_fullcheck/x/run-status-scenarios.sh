#!/bin/bash
# usage: run.sh outdir
out=$1; R=/home/user/youtube-subject-modify-auto
export PATH=$R/.harness-tmp/x/bin:$PATH
run(){ name=$1; shift; env "$@" $R/.harness-tmp/pwsh/pwsh -NoProfile -NonInteractive -File $R/web/scripts/status.ps1 > $out/$name.txt 2>&1; echo "exit=$?" >> $out/$name.txt; }
run full SHIM_MODE=full
run partial SHIM_MODE=partial
run empty SHIM_MODE=empty
run badport SHIM_MODE=badport
run psempty SHIM_MODE=psempty
run array SHIM_MODE=full SHIM_JSON=array
