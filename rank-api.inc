# ---- 独立影视榜单 API → 家庭服务器 8891 ----
location = /rank-api {
    return 308 https://$host/rank-api/;
}

location ^~ /rank-api/ {
    limit_req zone=pan_public burst=40 nodelay;
    proxy_pass http://127.0.0.1:18893/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "";
    proxy_connect_timeout 15s;
    proxy_read_timeout 90s;
    proxy_send_timeout 90s;
    proxy_buffering off;
    proxy_cache off;
    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header X-Content-Type-Options "nosniff" always;
}
