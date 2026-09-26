import Character from "./Character.jsx";

export default function StallScene({ agents, selectedId, talkingId, onSelect }) {
  return (
    <div className="stall-scene">
      {agents.map((agent) => {
        const isActive = agent.id === selectedId;
        return (
          <button
            key={agent.id}
            className={`stall ${isActive ? "stall-active" : ""}`}
            style={{ "--stall-accent": agent.theme.accent }}
            onClick={() => onSelect(agent.id)}
          >
            <Character
              theme={agent.theme}
              talking={talkingId === agent.id}
              active={isActive}
            />
            <div className="stall-sign">
              <span className="stall-name">{agent.stall_name}</span>
              <span className="stall-merchant">{agent.display_name}</span>
              <span className="stall-tagline">{agent.tagline}</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
