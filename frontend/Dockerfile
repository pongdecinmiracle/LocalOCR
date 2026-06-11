FROM nginx:1.27-alpine

# Serve the static SPA and reverse-proxy /api to the backend service.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.js styles.css /usr/share/nginx/html/

EXPOSE 80
