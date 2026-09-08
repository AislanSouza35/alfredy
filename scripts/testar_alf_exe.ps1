$ErrorActionPreference = 'Stop'

Get-Process ALF -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath 'dist\ALF\logs\alf_runtime_debug.log' -ErrorAction SilentlyContinue

$processo = Start-Process -FilePath (Resolve-Path 'dist\ALF\ALF.exe') -PassThru
Start-Sleep -Seconds 2

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = [System.Windows.Automation.AutomationElement]::RootElement
$janela = $null

for ($i = 0; $i -lt 30 -and $null -eq $janela; $i++) {
    $janelas = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition
    )

    foreach ($item in $janelas) {
        if ($item.Current.Name -eq 'ALF' -or $item.Current.ProcessId -eq $processo.Id) {
            $janela = $item
            break
        }
    }

    if ($null -eq $janela) {
        Start-Sleep -Milliseconds 500
    }
}

if ($null -eq $janela) {
    throw 'Janela ALF nao encontrada'
}

function Find-ButtonByName {
    param(
        [System.Windows.Automation.AutomationElement] $Parent,
        [string] $Name
    )

    $condicao = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button
    )
    $botoes = $Parent.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $condicao
    )

    foreach ($botao in $botoes) {
        if ($botao.Current.Name -eq $Name) {
            return $botao
        }
    }

    return $null
}

$botaoIniciar = Find-ButtonByName -Parent $janela -Name 'INICIAR CHAMADA'
if ($null -eq $botaoIniciar) {
    throw 'Botao INICIAR CHAMADA nao encontrado'
}

$botaoIniciar.GetCurrentPattern(
    [System.Windows.Automation.InvokePattern]::Pattern
).Invoke()

Start-Sleep -Seconds 18

$botaoTela = Find-ButtonByName -Parent $janela -Name 'ANALISAR TELA'
if ($null -ne $botaoTela) {
    $botaoTela.GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
}

Start-Sleep -Seconds 75

'PROCESSO'
Get-Process ALF -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, StartTime |
    Format-Table -AutoSize

'LOG_TAIL'
if (Test-Path -LiteralPath 'dist\ALF\logs\alf_runtime_debug.log') {
    Get-Content -LiteralPath 'dist\ALF\logs\alf_runtime_debug.log' -Tail 160
}

Get-Process ALF -ErrorAction SilentlyContinue | Stop-Process -Force
