#!/bin/bash
set -e

source /etc/profile

# check_table TABLE_NAME
# Returns 0 (true) if the table exists in the current database, 1 otherwise.
check_table() {
    local table="$1"
    local result
    case "${table}" in
        ''|*[!a-zA-Z0-9_]*)
            echo "check_table: invalid table name '${table}'" >&2
            return 1
            ;;
    esac
    result=$(gosu "${UWSGI_USER}" python manage.py dbshell 2>/dev/null <<EOF
SELECT COUNT(*) FROM information_schema.tables WHERE table_name='${table}';
EOF
)
    printf '%s\n' "${result}" | grep -q '^[[:space:]]*1[[:space:]]*$'
}

check_column() {
    local table="$1"
    local column="$2"
    local result
    result=$(gosu "${UWSGI_USER}" python manage.py dbshell 2>/dev/null <<EOF
SELECT COUNT(*) FROM information_schema.columns WHERE table_name='${table}' AND column_name='${column}';
EOF
)
    printf '%s\n' "${result}" | grep -q '^[[:space:]]*1[[:space:]]*$'
}

echo 'KoBoCAT initializing...'

cd "${KOBOCAT_SRC_DIR}"

if [[ -z $DATABASE_URL ]]; then
    echo "DATABASE_URL must be configured to run this server"
    echo "example: 'DATABASE_URL=postgres://hostname:5432/dbname'"
    exit 1
fi

# Handle Python dependencies BEFORE attempting any `manage.py` commands
KOBOCAT_WEB_SERVER="${KOBOCAT_WEB_SERVER:-uWSGI}"
if [[ "${KOBOCAT_WEB_SERVER,,}" == "uwsgi" ]]; then
    # `diff` returns exit code 1 if it finds a difference between the files
    if ! diff -q "${KOBOCAT_SRC_DIR}/dependencies/pip/requirements.txt" "${TMP_DIR}/pip_dependencies.txt"
    then
        echo "Syncing production pip dependencies..."
        pip-sync dependencies/pip/requirements.txt 1>/dev/null
        cp "dependencies/pip/requirements.txt" "${TMP_DIR}/pip_dependencies.txt"
    fi
else
    if ! diff -q "${KOBOCAT_SRC_DIR}/dependencies/pip/dev_requirements.txt" "${TMP_DIR}/pip_dependencies.txt"
    then
        echo "Syncing development pip dependencies..."
        pip-sync dependencies/pip/dev_requirements.txt 1>/dev/null
        cp "dependencies/pip/dev_requirements.txt" "${TMP_DIR}/pip_dependencies.txt"
    fi
fi

# Wait for databases to be up & running before going further
/bin/bash "${INIT_PATH}/wait_for_mongo.bash"
/bin/bash "${INIT_PATH}/wait_for_postgres.bash"

# Run migrations only on a clean deployment (no django_migrations table yet)
if ! check_table "django_migrations"; then
    echo 'Running migrations...'
    gosu "${UWSGI_USER}" python manage.py migrate --noinput
fi

# Run django_celery_beat migrations if clocked_id column is missing
if ! check_column "django_celery_beat_periodictask" "clocked_id"; then
    echo 'Running django_celery_beat migrations...'
    gosu "${UWSGI_USER}" python manage.py migrate django_celery_beat --noinput
fi

# Run main migrations if attachment_storage_bytes column is missing
if ! check_column "main_userprofile" "attachment_storage_bytes"; then
    echo 'Running main migrations...'
    gosu "${UWSGI_USER}" python manage.py migrate main --noinput
fi

echo 'Setting up cron tasks...'
/bin/bash "${KOBOCAT_SRC_DIR}/docker/setup_cron.bash"
/bin/bash "${KOBOCAT_SRC_DIR}/docker/setup_pydev_debugger.bash"
/bin/bash "${KOBOCAT_SRC_DIR}/docker/sync_static.bash"

echo 'Cleaning up Celery PIDs...'
rm -rf "${CELERY_PID_DIR}"/*.pid

echo 'KoBoCAT initialization complete.'

exec /usr/bin/runsvdir "${SERVICES_DIR}"
