# commands.md
I note some commands that might come handy. Nothing is related to the codebase.

## Docker Build Cache Remove
- `docker builder prune --force`
- `docker system prune --all --volumes --force` (Very aggressive)

## Other commands
- View dangling images in docker: `docker images -f 'dangling=true'`
- Docker build command: `docker build -t ridwan0110/find_my_iphone_automate:<version> .`
- Add `latest` tag in docker images: `ocker tag ridwan0110/find_my_iphone_automate:<version> ridwan0110/find_my_iphone_automate:latest`
