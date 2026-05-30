const clients = new Set();

function addClient(ws) {
  clients.add(ws);
  ws.on('close', () => clients.delete(ws));
}

function broadcast(event) {
  const msg = JSON.stringify(event);
  clients.forEach((c) => {
    if (c.readyState === 1) c.send(msg);
  });
}

module.exports = { addClient, broadcast };
