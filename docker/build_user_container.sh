docker buildx build --platform=linux/amd64,linux/arm64 --push -f docker/User-Env.Dockerfile -t metsi/watershed_workflow:master . && \
docker buildx build --platform=linux/amd64,linux/arm64 --push -f docker/ATS-User-Env.Dockerfile -t metsi/watershed_workflow-ats:master .

#docker build -f docker/User-Env.Dockerfile -t metsi/watershed_workflow:master . && \
#docker build -f docker/ATS-User-Env.Dockerfile -t metsi/watershed_workflow-ats:master .
