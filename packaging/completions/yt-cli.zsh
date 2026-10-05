#compdef yt-cli

_yt_cli_completion() {
  eval $(env _TYPER_COMPLETE_ARGS="${words[1,$CURRENT]}" _YT_CLI_COMPLETE=complete_zsh yt-cli)
}

compdef _yt_cli_completion yt-cli
