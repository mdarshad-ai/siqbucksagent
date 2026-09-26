import { useEffect, useState } from "react";
import { fetchAgents } from "./api.js";
import StallScene from "./components/StallScene.jsx";
import ChatPanel from "./components/ChatPanel.jsx";

export default function App() {
  const [agents, setAgents] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [talkingId, setTalkingId] = useState(null);
  const [histories, setHistories] = useState({}); // agentId -> turns[]
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    fetchAgents()
      .then((data) => {
        setAgents(data);
        if (data.length > 0) setSelectedId(data[0].id);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  const selectedAgent = agents.find((a) => a.id === selectedId);

  return (
    <div className="app-root">
      <header className="app-header">
        <h1>The Gem Exchange</h1>
        <p>Two counters, two dealers. Walk up and ask about what they're carrying.</p>
      </header>

      {loadError && (
        <div className="chat-error" style={{ margin: "0 auto 1rem" }}>
          Couldn't reach the backend: {loadError}
        </div>
      )}

      {agents.length > 0 && (
        <StallScene
          agents={agents}
          selectedId={selectedId}
          talkingId={talkingId}
          onSelect={setSelectedId}
        />
      )}

      {selectedAgent && (
        <ChatPanel
          key={selectedAgent.id}
          agent={selectedAgent}
          history={histories[selectedAgent.id] || []}
          setHistory={(h) =>
            setHistories((prev) => ({ ...prev, [selectedAgent.id]: h }))
          }
          onTalkingChange={(isTalking) =>
            setTalkingId(isTalking ? selectedAgent.id : null)
          }
        />
      )}
    </div>
  );
}
