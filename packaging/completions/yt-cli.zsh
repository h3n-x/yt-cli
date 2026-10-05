#compdef yt-cli

# Completado zsh para yt-cli, delegando en el motor dinámico de Click/Typer.
_yt_cli_completion() {
    local -a completions
    local -a completions_with_descriptions
    local -a response

    response=("${(@f)$(env COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT - 1)) \
        _YT_CLI_COMPLETE=zsh_complete yt-cli)}")

    for type_and_value in $response; do
        completions_with_descriptions+=("${type_and_value#*,}")
        completions+=("${type_and_value#*,}")
    done

    if [ -n "$completions_with_descriptions" ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi
    if [ -n "$completions" ]; then
        compadd -U -V unsorted -a completions
    fi
}

compdef _yt_cli_completion yt-cli
