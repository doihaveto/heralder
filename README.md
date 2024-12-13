# Heralder

Heralder converts long-form articles or essays (or any text) into audio and generates an RSS podcast feed that can be used in any podcasting app.

## Features

- **Browser Addon**: Add articles and essays to Heralder from your browser.
- **Supported TTS Providers**:
  - Microsoft Edge TTS - default provider, free.
  - Amazon Polly - free tier with limited monthly quota - **recommended.**
  - Google TTS - free tier with limited monthly quota.
- **RSS feed**: Listen to your content in your favourite podcasting app.

## Screenshot
![Screenshot](https://github.com/doihaveto/heralder/blob/main/screenshot.png?raw=true)
## Installation
### Docker
An example docker-compose file:
```
services:
  heralder:
    image: ghcr.io/doihaveto/heralder
    container_name: heralder
    environment:
      - PUID=1000
      - PGID=1000
      - URL=http://localhost:8000
    volumes:
      - ./heralder/data:/data
    ports:
      - 8000:6468
    depends_on:
      - redis
    restart: unless-stopped 

  redis:
    image: redis:alpine
    container_name: redis
    restart: unless-stopped 
```
#### Environment variables

| Variable       | Description                                                                  | Default value         |
| -------------- | ---------------------------------------------------------------------------- | --------------------- |
| PUID           | User id to run as (run `id $user` to get your current user's id)             | -                     |
| PGID           | User group id to run as (run `id $user` to get your current user's group id) | -                     |
| URL            | URL that Heralder will be accessed from                                      | http://localhost:6468 |
| REDIS_HOSTNAME | Redis hostname                                                               | redis                 |
| REDIS_PORT     | Redis port                                                                   | 6379                  |
| REDIS_DB       | Redis database                                                               | 0                     |

The default username password is `admin:admin`. It can be changed from the dashboard.
