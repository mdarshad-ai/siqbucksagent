import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAgents, fetchFeatured, routeQuestion, streamChat } from "./api.js";
import { friendlyChatError } from "./chatErrors.js";
import { loadHistory, saveHistory } from "./chatStore.js";
import CounterView from "./counter/CounterView.jsx";
import {
  ClosingCall,
  Hero,
  HowItWorks,
  OnTheCounter,
  Partners,
  SiteFooter,
  SiteHeader,
} from "./site/Sections.jsx";

export default function App() {
  const [agents, setAgents] = useState([]);
  const [featured, setFeatured] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [histories, setHistories] = useState({}); // agentId -> turns
  const [restored, setRestored] = useState({}); // agentId -> came from a past visit
  const [counterId, setCounterId] = useState(null); // open chat, or null
  const [lastId, setLastId] = useState(null);
  const [live, setLive] = useState(null); // {agentId, turn} while a reply streams
  const [errors, setErrors] = useState({});
  const [showFloat, setShowFloat] = useState(false);
  const busyRef = useRef(false);

  useEffect(() => {
    fetchAgents()
      .then((list) => {
        setAgents(list);
        const saved = {};
        for (const a of list) saved[a.id] = loadHistory(a.id);
        setHistories(saved);
        setRestored(Object.fromEntries(list.map((a) => [a.id, saved[a.id].length > 0])));
      })
      .catch((err) => setLoadError(err.message));
    fetchFeatured().then(setFeatured);
  }, []);

  useEffect(() => {
    const onScroll = () => setShowFloat(window.scrollY > window.innerHeight * 0.6);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // The chat covers the page, so stop the page scrolling underneath.
  useEffect(() => {
    if (!counterId) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [counterId]);

  const setHistory = useCallback((agentId, turns) => {
    setHistories((prev) => ({ ...prev, [agentId]: turns }));
    saveHistory(agentId, turns);
  }, []);

  const sendMessage = useCallback(
    async (agentId, message) => {
      if (busyRef.current) return false;
      const agent = agents.find((a) => a.id === agentId);
      if (!agent) return false;
      busyRef.current = true;
      const before = histories[agentId] || [];
      setErrors((e) => ({ ...e, [agentId]: null }));
      setHistories((prev) => ({ ...prev, [agentId]: [...before, { role: "user", content: message }] }));

      const turn = { role: "assistant", content: "", cards: [], streaming: true };
      const update = (fields) => {
        Object.assign(turn, fields);
        setLive({ agentId, turn: { ...turn } });
      };
      update({});
      try {
        const done = await streamChat(agentId, message, before, {
          onDelta: (text) => update({ content: turn.content + text }),
          onCard: (card) => update({ cards: [...turn.cards, card] }),
        });
        setHistory(agentId, done.history);
        return true;
      } catch (err) {
        setHistories((prev) => ({ ...prev, [agentId]: before }));
        setErrors((e) => ({ ...e, [agentId]: friendlyChatError(err, agent.display_name) }));
        return false;
      } finally {
        busyRef.current = false;
        setLive(null);
      }
    },
    [agents, histories, setHistory]
  );

  function openCounter(agentId, message) {
    const id = agentId || lastId || agents[0]?.id;
    if (!id) return;
    setCounterId(id);
    setLastId(id);
    if (message) sendMessage(id, message);
  }

  async function askFromSite(message) {
    const id = (await routeQuestion(message)) || agents[0]?.id;
    openCounter(id, message);
  }

  function handoff(h) {
    setRestored((r) => ({ ...r, [h.to]: false }));
    openCounter(h.to, h.message);
  }

  const counterAgent = agents.find((a) => a.id === counterId);

  return (
    <div className="site">
      <SiteHeader onTalk={() => openCounter()} />
      <main>
        {loadError && (
          <div className="site-container load-error">
            We couldn't open the shop just now ({loadError}). Please refresh in a moment.
          </div>
        )}
        <Hero agents={agents} onAsk={askFromSite} onTalk={(id) => openCounter(id)} />
        <Partners agents={agents} onTalk={(id) => openCounter(id)} onAskPartner={openCounter} />
        <OnTheCounter stones={featured} onAskPartner={openCounter} />
        <HowItWorks />
        <ClosingCall onAsk={askFromSite} />
      </main>
      <SiteFooter />

      {showFloat && !counterId && agents.length > 0 && (
        <button className="float-talk" onClick={() => openCounter()}>
          <span className="float-talk-dot" aria-hidden="true" />
          Talk to an AI partner
        </button>
      )}

      {counterAgent && (
        <CounterView
          agents={agents}
          agent={counterAgent}
          history={histories[counterAgent.id] || []}
          live={live?.agentId === counterAgent.id ? live.turn : null}
          busy={Boolean(live)}
          error={errors[counterAgent.id]}
          restored={restored[counterAgent.id]}
          onSend={(message) => sendMessage(counterAgent.id, message)}
          onSwitch={(id) => {
            setCounterId(id);
            setLastId(id);
          }}
          onClose={() => setCounterId(null)}
          onHandoff={handoff}
          onStartFresh={() => {
            setHistory(counterAgent.id, []);
            setRestored((r) => ({ ...r, [counterAgent.id]: false }));
          }}
        />
      )}
    </div>
  );
}
