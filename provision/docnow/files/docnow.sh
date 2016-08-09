export VIRTUAL_ENV=/opt/docnow
export PATH="$VIRTUAL_ENV/bin:$PATH"
unset PYTHON_HOME
exec "${@:-$SHELL}"
