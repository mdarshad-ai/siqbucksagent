// Chat limit messages in the partner's own voice rather than a bare error.

function waitText(seconds) {
  const minutes = Math.ceil((seconds || 60) / 60);
  return minutes <= 1 ? "a minute" : `${minutes} minutes`;
}

export function friendlyChatError(err, name) {
  if (err.code === "slow_down") {
    return `${name} sets down the loupe. "Give me ${waitText(err.retryAfter)}, then ask me again."`;
  }
  if (err.code === "daily") {
    return `${name} smiles. "That's plenty of questions for one day. Come back tomorrow and I'll be here."`;
  }
  if (err.code === "closed") {
    return "The counters are closed for tonight. Please come back tomorrow.";
  }
  return err.message;
}
