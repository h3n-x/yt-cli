# Completado fish para yt-cli, delegando en el motor dinámico de Click/Typer.
function _yt_cli_completion
    set -l response (env _YT_CLI_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) yt-cli)

    for completion in $response
        set -l metadata (string split "," $completion)

        if test $metadata[1] = "dir"
            __fish_complete_directories $metadata[2]
        else if test $metadata[1] = "file"
            __fish_complete_path $metadata[2]
        else if test $metadata[1] = "plain"
            echo $metadata[2]
        end
    end
end

complete --no-files --command yt-cli --arguments "(_yt_cli_completion)"
