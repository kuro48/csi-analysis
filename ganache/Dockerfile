FROM node:18-alpine

RUN npm install -g ganache@7

EXPOSE 8545

CMD ["ganache", "--host", "0.0.0.0", "--port", "8545"]
