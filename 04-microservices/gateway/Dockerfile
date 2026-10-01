# The API gateway (JavaScript, Node.js; no packages, so no npm install). compose.yaml gives the
# data as the build context "data".
FROM node:24-alpine
WORKDIR /app
COPY --from=data users.csv ./
COPY package.json gateway.js ./
EXPOSE 8000
CMD ["node", "gateway.js"]
