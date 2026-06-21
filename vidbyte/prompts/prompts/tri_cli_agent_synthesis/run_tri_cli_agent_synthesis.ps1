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
    [string]$Stdout
    [string]$Stderr

    AgentCommandResult([string]$Name, [string]$Status, [int]$ExitCode, [string]$Stdout, [string]$Stderr) {
        # Stores one agent command result for later Markdown rendering.
        $this.Name = $Name
        $this.Status = $Status
        $this.ExitCode = $ExitCode
        $this.Stdout = $Stdout
        $this.Stderr = $Stderr
    }

    [string] ToSummaryRow() {
        # Formats this result as one row in the summary table.
        return "| $($this.Name) | $($this.Status) | $($this.ExitCode) |"
    }

    [string] ToMarkdownSection() {
        # Formats this result as a stable Markdown section for host-agent synthesis.
        $safeStdout = if ([string]::IsNullOrWhiteSpace($this.Stdout)) { "(no stdout)" } else { $this.Stdout.Trim() }
        $safeStderr = if ([string]::IsNullOrWhiteSpace($this.Stderr)) { "(no stderr)" } else { $this.Stderr.Trim() }
        return "## $($this.Name)`n`nStatus: $($this.Status)`nExit code: $($this.ExitCode)`n`n### stdout`n`n``````text`n$safeStdout`n```````n`n### stderr`n`n``````text`n$safeStderr`n``````"
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
        $promptFile = $this.WritePromptFile($candidatePrompt)
        try {
            return @(
                $this.InvokeAgent("codex", "codex", @("exec", "-m", $this.CodexModel, "-c", "model_reasoning_effort=`"$($this.CodexThinking)`"", "--sandbox", "read-only", "-a", "never", "--color", "never", "--cd", $this.WorkingDirectory, "-"), $candidatePrompt, $true),
                $this.InvokeAgent("claude_code", "claude", @("--print", "--model", $this.ClaudeModel, "--effort", $this.ClaudeThinking, "--permission-mode", "dontAsk", "--tools", "", "--add-dir", $this.WorkingDirectory), $candidatePrompt, $true),
                $this.InvokeAgent("opencode", "opencode", @("run", "--model", $this.OpencodeModel, "--variant", $this.OpencodeThinking, "--dir", $this.WorkingDirectory, "--file", $promptFile, "Read the attached prompt file and return only your candidate answer."), "", $false)
            )
        } finally {
            Remove-Item -LiteralPath $promptFile -Force -ErrorAction SilentlyContinue
        }
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

    [string] WritePromptFile([string]$Content) {
        # Writes prompt content to a temporary UTF-8 file for CLIs that prefer file input.
        $path = Join-Path ([System.IO.Path]::GetTempPath()) ("tri-cli-agent-synthesis-" + [System.Guid]::NewGuid().ToString("N") + ".md")
        [System.IO.File]::WriteAllText($path, $Content, [System.Text.Encoding]::UTF8)
        return $path
    }

    [AgentCommandResult] InvokeAgent([string]$Name, [string]$Command, [string[]]$Arguments, [string]$InputText, [bool]$UseStdin) {
        # Executes one CLI command, captures stdout and stderr separately, and returns a result section.
        $commandInfo = Get-Command -Name $Command -ErrorAction SilentlyContinue
        if (-not $commandInfo) {
            return [AgentCommandResult]::new($Name, "missing_command", 127, "", "Command not found: $Command")
        }

        try {
            $launch = $this.BuildLaunch($commandInfo, $Arguments)
            $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
            $startInfo.FileName = $launch["FileName"]
            $startInfo.Arguments = $this.JoinArguments($launch["Arguments"])
            $startInfo.WorkingDirectory = $this.WorkingDirectory
            $startInfo.UseShellExecute = $false
            $startInfo.RedirectStandardInput = $UseStdin
            $startInfo.RedirectStandardOutput = $true
            $startInfo.RedirectStandardError = $true

            $process = [System.Diagnostics.Process]::new()
            $process.StartInfo = $startInfo
            $null = $process.Start()
            if ($UseStdin) {
                $process.StandardInput.Write($InputText)
                $process.StandardInput.Close()
            }
            $stdoutTask = $process.StandardOutput.ReadToEndAsync()
            $stderrTask = $process.StandardError.ReadToEndAsync()
            $process.WaitForExit()
            $status = if ($process.ExitCode -eq 0) { "ok" } else { "failed" }
            return [AgentCommandResult]::new($Name, $status, $process.ExitCode, $stdoutTask.Result, $stderrTask.Result)
        } catch {
            return [AgentCommandResult]::new($Name, "failed", 1, "", $_.Exception.Message)
        }
    }

    [hashtable] BuildLaunch([object]$CommandInfo, [string[]]$Arguments) {
        # Resolves scripts and native executables into a process filename plus arguments.
        $source = $CommandInfo.Source
        if ($source.EndsWith(".ps1", [System.StringComparison]::OrdinalIgnoreCase)) {
            return @{ FileName = "powershell.exe"; Arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $source) + $Arguments }
        }
        return @{ FileName = $source; Arguments = $Arguments }
    }

    [string] JoinArguments([string[]]$Arguments) {
        # Converts an argument array into a Windows process argument string.
        return ($Arguments | ForEach-Object { $this.QuoteArgument($_) }) -join " "
    }

    [string] QuoteArgument([string]$Argument) {
        # Quotes one argument for CreateProcess without invoking a shell.
        if ($null -eq $Argument) {
            return '""'
        }
        if ($Argument -notmatch '[\s"]') {
            return $Argument
        }

        $builder = [System.Text.StringBuilder]::new()
        [void]$builder.Append('"')
        $backslashes = 0
        foreach ($character in $Argument.ToCharArray()) {
            if ($character -eq '\') {
                $backslashes += 1
            } elseif ($character -eq '"') {
                [void]$builder.Append("\" * (($backslashes * 2) + 1))
                [void]$builder.Append('"')
                $backslashes = 0
            } else {
                if ($backslashes -gt 0) {
                    [void]$builder.Append("\" * $backslashes)
                    $backslashes = 0
                }
                [void]$builder.Append($character)
            }
        }
        if ($backslashes -gt 0) {
            [void]$builder.Append("\" * ($backslashes * 2))
        }
        [void]$builder.Append('"')
        return $builder.ToString()
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
