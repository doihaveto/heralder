#!/bin/bash

# Set the user and group IDs
USER_ID=${PUID:-tts}
GROUP_ID=${PGID:-tts}

# Check if the group ID already exists
if ! getent group $GROUP_ID > /dev/null 2>&1; then
    echo "Creating group: $GROUP_ID"
    groupadd -g $GROUP_ID tts
fi

# Check if the user ID already exists
if ! id -u $USER_ID > /dev/null 2>&1; then
    echo "Creating user: $USER_ID"
    useradd -u $USER_ID -g $GROUP_ID -s /bin/bash -m tts
fi

# Change the ownership of /data
chown -R $USER_ID:$GROUP_ID /data

# Generate a flask secret key
SECRET_KEY_FILE="/data/.secret_key"

# Check if the secret key file exists
if [ ! -f "$SECRET_KEY_FILE" ]; then
    echo "Secret key file does not exist. Creating it now..."
    
    # Generate a random secret key (you can modify this command to use your preferred method)
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
    
    # Write the secret key to the file
    echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
    echo "Secret key has been written to $SECRET_KEY_FILE"
fi

# run flask db commands
if [ ! -d "/data/migrations" ]; then
    echo "Initialising database..."
    su -s /bin/bash tts -c "exec flask db init -d /data/migrations"
fi

echo "Migrating database..."
su -s /bin/bash tts -c "exec flask db migrate -d /data/migrations"
echo "Upgrading database..."
su -s /bin/bash tts -c "exec flask db upgrade -d /data/migrations"

echo "Running supervisor"
supervisord -c /etc/supervisor/conf.d/supervisord.conf
