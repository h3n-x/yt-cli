# Completado bash para yt-cli.
# Se apoya en el motor de completado dinámico de Click/Typer: en vez de
# mantener a mano una lista de subcomandos que se desincroniza del código,
# se le pide al propio binario que genere sus opciones en tiempo real.
_yt_cli_completion() {
    local IFS=$'\n'
    local response

    response=$(env COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD="$COMP_CWORD" \
        _YT_CLI_COMPLETE=bash_complete "${COMP_WORDS[0]}")

    for completion in $response; do
        IFS=',' read -r type value <<< "$completion"
        if [[ $type == "dir" ]]; then
            COMPREPLY=()
            compopt -o dirnames 2>/dev/null || true
        elif [[ $type == "file" ]]; then
            COMPREPLY=()
            compopt -o default 2>/dev/null || true
        elif [[ $type == "plain" ]]; then
            COMPREPLY+=("$value")
        fi
    done

    return 0
}

complete -o nosort -F _yt_cli_completion yt-cli
