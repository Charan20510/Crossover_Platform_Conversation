FROM node:20-slim

WORKDIR /app

# Install dependencies
COPY package.json .
RUN npm install --production

# Copy source
COPY . .

# Create auth states directory
RUN mkdir -p auth_states

EXPOSE 3000

CMD ["node", "index.js"]
