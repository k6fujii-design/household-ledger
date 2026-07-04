FROM node:22-alpine

WORKDIR /app
COPY package.json ./
RUN npm install

COPY index.html ./
COPY tsconfig.json ./
COPY vite.config.ts ./
COPY src ./src

CMD ["npm", "run", "dev"]
