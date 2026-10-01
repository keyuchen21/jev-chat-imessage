#!/bin/sh
# Shared by start.command and the packaged launcher. Source this file, then call
# jev_ensure_uv LOG_PATH. Failures leave a user-facing reason in JEV_UV_ERROR.

jev_load_env() {
    # Let Python load editable context settings from their file, without mistaking
    # sourced exports for external overrides. Locals restore any inherited values
    # on return; other settings (including shell/keychain credentials) still export.
    local JEV_HISTORY JEV_CONTEXT_MESSAGES
    if [ -f "$1" ]; then
        . "$1"
    fi
}

jev_check_arch() {
    # torch (>=2.14) ships no macOS x86_64 wheel, so an x86_64 process would only
    # die later in `uv sync` with an opaque resolver error (issue #19). Both launch
    # entries call this before any install work; failure sets JEV_ARCH_ERROR.
    # On a real Intel Mac `sysctl sysctl.proc_translated` fails (unknown oid), so
    # the empty/failed output falls through to the Intel branch.
    JEV_ARCH_ERROR=""
    [ "$(uname -m)" = "x86_64" ] || return 0
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || true)" = "1" ]; then
        JEV_ARCH_ERROR="This app is running under Rosetta (Intel translation). Start it natively on ARM: in Terminal, leave the x86_64 shell and run again from a native one; for the .app, choose Get Info and clear 'Open using Rosetta', then try again."
    else
        JEV_ARCH_ERROR="This app supports Apple Silicon (M-series) Macs only: torch, which the local judge model needs, has no Intel Mac build."
    fi
    return 1
}

jev_ensure_uv() {
    local uv_log="$1" install_script="" curl_code=0 install_code=0 brew_code=0
    JEV_UV_ERROR=""
    if command -v uv >/dev/null 2>&1 && uv --version >/dev/null 2>&1; then
        return 0
    fi

    printf '%s\n' 'uv is not available; downloading and running the official install script' >> "$uv_log"
    if install_script=$(mktemp "${TMPDIR:-/tmp}/jev-uv.XXXXXX"); then
        # Download completely before execution: curl | sh can report success when
        # curl fails, or execute a truncated script. Keep curl's original exit code.
        if curl -LsSf --connect-timeout 10 --max-time 60 \
                --retry 2 --retry-delay 1 --retry-max-time 120 \
                -o "$install_script" https://astral.sh/uv/install.sh >> "$uv_log" 2>&1; then
            # Pin the destination to the PATH used by both Finder and source runs;
            # do not depend on a shell-profile edit taking effect in this process.
            if UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 \
                    sh "$install_script" >> "$uv_log" 2>&1; then
                if command -v uv >/dev/null 2>&1 && uv --version >> "$uv_log" 2>&1; then
                    rm -f "$install_script"
                    return 0
                fi
                JEV_UV_ERROR="The official install script finished, but uv is still not available"
            else
                install_code=$?
                JEV_UV_ERROR="The official uv install script failed (exit code $install_code); check the log for download or permission errors"
            fi
        else
            curl_code=$?
            case "$curl_code" in
                28) JEV_UV_ERROR="Download of the uv install script timed out; check your network or proxy" ;;
                5|6) JEV_UV_ERROR="Could not resolve the uv download host or proxy; check DNS and proxy settings" ;;
                7) JEV_UV_ERROR="Could not connect to the uv download server; check your network or proxy" ;;
                35|60) JEV_UV_ERROR="TLS/certificate check failed for the uv download; check the system clock, certificates or proxy" ;;
                22) JEV_UV_ERROR="The uv download server returned an HTTP error; see the log" ;;
                23) JEV_UV_ERROR="Could not save the uv install script; check disk space and temp folder permissions" ;;
                *) JEV_UV_ERROR="Download of the uv install script failed (curl exit code $curl_code); see the log" ;;
            esac
        fi
        rm -f "$install_script"
    else
        JEV_UV_ERROR="Could not create a temp file for the uv install; check temp folder permissions and disk space"
    fi

    printf '%s\n' "$JEV_UV_ERROR" >> "$uv_log"
    if command -v brew >/dev/null 2>&1; then
        printf '%s\n' 'Trying to install uv with the installed Homebrew' >> "$uv_log"
        if CI=1 NONINTERACTIVE=1 HOMEBREW_NO_AUTO_UPDATE=1 \
                brew install uv >> "$uv_log" 2>&1; then
            if command -v uv >/dev/null 2>&1 && uv --version >> "$uv_log" 2>&1; then
                JEV_UV_ERROR=""
                return 0
            fi
            JEV_UV_ERROR="$JEV_UV_ERROR; after the Homebrew install uv is still not available, check PATH"
        else
            brew_code=$?
            JEV_UV_ERROR="$JEV_UV_ERROR; the Homebrew install also failed (exit code $brew_code)"
        fi
    else
        JEV_UV_ERROR="$JEV_UV_ERROR; Homebrew not found"
    fi
    printf '%s\n' "$JEV_UV_ERROR" >> "$uv_log"
    return 1
}
