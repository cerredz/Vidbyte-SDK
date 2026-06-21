param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,
    [string]$WorkingDirectory = (Get-Location).Path,
    [string]$CodexModel = "gpt-5.5",
    [string]$CodexThinking = "high",
    [string]$ClaudeModel = "opus-4.8",
    [string]$ClaudeThinking = "xhigh",
    [string]$OpencodeModel = "glm-5.2",
    [string]$OpencodeThinking = "max"
)

class AgentCommandResult {
    [string]$Name
    [string]$Status
    [int]$ExitCode
    [string]$Output

    AgentCommandResult([string]$Name, [string]$Status, [int]$ExitCode, [string]$Output) {
        # Stores one agent command result for later Markdown rendering.
        $this.Name = $Name
        $this.Status = $Status
        $this.ExitCode = $ExitCode
        $this.Output = $Output
    }

    [string] ToSummaryRow() {
        # Formats this result as one row in the summary table.
        return "| $($this.Name) | $($this.Status) | $($this.ExitCode) |"
    }

    [string] ToMarkdownSection() {
        # Formats this result as a stable Markdown section for host-agent synthesis.
        $safeOutput = if ([string]::IsNullOrWhiteSpace($this.Output)) { "(no output)" } else { $this.Output.Trim() }
        return "## $($this.Name)`n`nStatus: $($this.Status)`nExit code: $($this.ExitCode)`n`n``````text`n$safeOutput`n``````"
    }
}

class TriCliAgentSynthesisRunner {
    [string]$Prompt
    [string]$WorkingDirectory
    [string]$CodexModel
    [string]$CodexThinking
    [string]$ClaudeModel
    [string]$ClaudeThinking
    [string]$OpencodeModel
    [string]$OpencodeThinking

    TriCliAgentSynthesisRunner([string]$Prompt, [string]$WorkingDirectory, [string]$CodexModel, [string]$CodexThinking, [string]$ClaudeModel, [string]$ClaudeThinking, [string]$OpencodeModel, [string]$OpencodeThinking) {
        # Captures the prompt, workspace, models, and thinking settings for the run.
        $this.Prompt = $Prompt
        $this.WorkingDirectory = $WorkingDirectory
        $this.CodexModel = $CodexModel
        $this.CodexThinking = $CodexThinking
        $this.ClaudeModel = $ClaudeModel
        $this.ClaudeThinking = $ClaudeThinking
        $this.OpencodeModel = $OpencodeModel
        $this.OpencodeThinking = $OpencodeThinking
    }

    [AgentCommandResult[]] Run() {
        # Runs every configured CLI independently and returns their captured results.
        $this.AssertWorkingDirectoryExists()
        $candidatePrompt = $this.BuildCandidatePrompt()
        return @(
            $this.InvokeAgent("codex", "codex", @("exec", "-m", $this.CodexModel, "-c", "model_reasoning_effort=`"$($this.CodexThinking)`"", "--sandbox", "read-only", "-a", "never", "--color", "never", "--cd", $this.WorkingDirectory, "-"), $candidatePrompt, $true),
            $this.InvokeAgent("claude_code", "claude", @("--print", "--model", $this.ClaudeModel, "--effort", $this.ClaudeThinking, "--permission-mode", "dontAsk", "--tools", "", "--add-dir", $this.WorkingDirectory), $candidatePrompt, $true),
            $this.InvokeAgent("opencode", "opencode", @("run", "--model", $this.OpencodeModel, "--variant", $this.OpencodeThinking, "--dir", $this.WorkingDirectory, $candidatePrompt), "", $false)
        )
    }

    [void] AssertWorkingDirectoryExists() {
        # Fails early when the requested working directory is not present.
        if (-not (Test-Path -LiteralPath $this.WorkingDirectory -PathType Container)) {
            throw "Working directory does not exist: $($this.WorkingDirectory)"
        }
    }

    [string] BuildCandidatePrompt() {
        # Wraps the user's prompt with side-effect boundaries for candidate agents.
        return @"
You are one candidate responder in a multi-agent synthesis workflow.

Answer the user's prompt directly and independently. Do not modify files, run destructive commands, create commits, open pull requests, or ask follow-up questions unless the prompt cannot be answered without them. Return only your candidate answer.

User prompt:
$($this.Prompt)
"@
    }

    [AgentCommandResult] InvokeAgent([string]$Name, [string]$Command, [string[]]$Arguments, [string]$InputText, [bool]$UseStdin) {
        # Executes one CLI command, captures output, and converts failures into result sections.
        if (-not (Get-Command -Name $Command -ErrorAction SilentlyContinue)) {
            return [AgentCommandResult]::new($Name, "missing_command", 127, "Command not found: $Command")
        }

        $previousLocation = Get-Location
        try {
            Set-Location -LiteralPath $this.WorkingDirectory
            if ($UseStdin) {
                $rawOutput = $InputText | & $Command @Arguments 2>&1
            } else {
                $rawOutput = & $Command @Arguments 2>&1
            }
            $exitCode = if ($global:LASTEXITCODE -is [int]) { $global:LASTEXITCODE } else { 0 }
            $status = if ($exitCode -eq 0) { "ok" } else { "failed" }
            return [AgentCommandResult]::new($Name, $status, $exitCode, $this.JoinOutput($rawOutput))
        } catch {
            return [AgentCommandResult]::new($Name, "failed", 1, $_.Exception.Message)
        } finally {
            Set-Location -LiteralPath $previousLocation.Path
        }
    }

    [string] JoinOutput([object[]]$RawOutput) {
        # Converts PowerShell output objects into a stable text block.
        if ($null -eq $RawOutput -or $RawOutput.Count -eq 0) {
            return ""
        }
        return ($RawOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    }

    [void] WriteReport([AgentCommandResult[]]$Results) {
        # Writes a stable Markdown report for the host agent to synthesize.
        Write-Output "# Tri-CLI Agent Synthesis Results"
        Write-Output ""
        Write-Output "| Agent | Status | Exit Code |"
        Write-Output "| --- | --- | --- |"
        foreach ($result in $Results) {
            Write-Output $result.ToSummaryRow()
        }
        Write-Output ""
        foreach ($result in $Results) {
            Write-Output $result.ToMarkdownSection()
            Write-Output ""
        }
    }
}

$runner = [TriCliAgentSynthesisRunner]::new(
    $Prompt,
    $WorkingDirectory,
    $CodexModel,
    $CodexThinking,
    $ClaudeModel,
    $ClaudeThinking,
    $OpencodeModel,
    $OpencodeThinking
)
$results = $runner.Run()
$runner.WriteReport($results)
