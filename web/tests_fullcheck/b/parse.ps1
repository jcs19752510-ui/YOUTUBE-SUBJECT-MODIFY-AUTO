param([string]$Dir)
$bad=@('Coalesce','Ternary','PipelineChain','NullConditional')
foreach($f in Get-ChildItem $Dir -Filter *.ps1 | Sort-Object Name){
  $t=$null;$e=$null
  $ast=[System.Management.Automation.Language.Parser]::ParseFile($f.FullName,[ref]$t,[ref]$e)
  $bytes=[IO.File]::ReadAllBytes($f.FullName)
  $bom=($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
  $nonascii=($bytes | Where-Object {$_ -gt 127}).Count -gt 0
  $v7=@()
  $v7+=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.TernaryExpressionAst]},$true) | %{ "ternary@"+$_.Extent.StartLineNumber }
  $v7+=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.PipelineChainAst]},$true) | %{ "chain@"+$_.Extent.StartLineNumber }
  $v7+=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.BinaryExpressionAst] -and $n.Operator -in 'QuestionQuestion'},$true) | %{ "??@"+$_.Extent.StartLineNumber }
  $v7+=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.MemberExpressionAst] -and $n.NullConditional},$true) | %{ "?.@"+$_.Extent.StartLineNumber }
  $v7+=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandParameterAst] -and $n.ParameterName -in 'Parallel','AsByteStream','AsPlainText','NoNewline','Remove'},$true) | ?{$_.ParameterName -in 'Parallel','AsByteStream'} | %{ "-"+$_.ParameterName+"@"+$_.Extent.StartLineNumber }
  $last=$bytes[-1]
  "{0}|errors={1}|bom={2}|nonascii={3}|v7={4}|crlf={5}" -f $f.Name,$e.Count,$bom,$nonascii,($v7 -join ','),([Text.Encoding]::UTF8.GetString($bytes) -match "`r`n")
  $e | %{ "  ERR "+$_.Extent.StartLineNumber+": "+$_.Message }
}
