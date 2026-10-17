FROM node:24-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG REACT_APP_API_URL=http://localhost:6767
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ARG REACT_APP_DEMO_MODE=true
ENV REACT_APP_DEMO_MODE=$REACT_APP_DEMO_MODE
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
