# ---------------------------------------------------------------------------
# Frontend image - Nginx + static UI
# Pinned, small (alpine-based) Nginx version.
# ---------------------------------------------------------------------------
FROM nginx:1.27.3-alpine

# Replace the default configuration with ours.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the static UI into the web server's document root.
COPY static/ /usr/share/nginx/html/

EXPOSE 80
# CMD comes from the base image: nginx -g 'daemon off;'
