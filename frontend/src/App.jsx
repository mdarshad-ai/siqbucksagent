import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAgents, fetchFeatured, streamChat } from "./api.js";
import { friendlyChatError } from "./chatErrors.js";
import { loadHistory, saveHistory } from "./chatStore.js";
import { previewHandlers } from "./components/PreviewCard.jsx";
import CataloguePage from "./catalogue/CataloguePage.jsx";
import StonePage from "./catalogue/StonePage.jsx";
import CounterView from "./counter/CounterView.jsx";
import { matchRoute, useLocation } from "./router.jsx";
import {
  ClosingCall,
  Hero,
  HowItWorks,
  MeetExpert,
  OnTheCounter,
  SiteFooter,
  SiteHeader,
} from "./site/Sections.jsx";

export default function App() {
  const [expert, setExpert] = useState(null); // the shop's one AI partner
  const [featured, setFeatured] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [history, setHistoryState] = useState([]);
  const [restored, setRestored] = useState(false); // chat came from a past visit
  const [open, setOpen] = useState(false); // the chat overlay
  const [live, setLive] = useState(null); // the reply while it streams
  const [error, setError] = useState(null);
  const [showFloat, setShowFloat] = useState(false);
  const busyRef = useRef(false);
  const location = useLocation();
  const route = matchRoute(location.path);

  // Following a link (e.g. "View details" on a stone card) closes the chat.
  useEffect(() => {
    setOpen(false);
  }, [location.path]);

  useEffect(() => {
    fetchAgents()
      .then((list) => {
        const first = list[0] || null;
        setExpert(first);
        if (first) {
          const saved = loadHistory(first.id);
          setHistoryState(saved);
          setRestored(saved.length > 0);
        }
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
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const setHistory = useCallback(
    (turns) => {
      setHistoryState(turns);
      if (expert) saveHistory(expert.id, turns);
    },
    [expert]
  );

  const sendMessage = useCallback(
    async (message) => {
      if (busyRef.current || !expert) return false;
      busyRef.current = true;
      const before = history;
      setError(null);
      setHistoryState([...before, { role: "user", content: message }]);

      const turn = { role: "assistant", content: "", cards: [], images: [], streaming: true };
      const update = (fields) => {
        Object.assign(turn, fields);
        setLive({ ...turn });
      };
      update({});
      try {
        const done = await streamChat(expert.id, message, before, {
          onDelta: (text) => update({ content: turn.content + text }),
          onCard: (card) => update({ cards: [...turn.cards, card] }),
          ...previewHandlers(turn, update),
        });
        setHistory(done.history);
        return true;
      } catch (err) {
        setHistoryState(before);
        setError(friendlyChatError(err, expert.display_name));
        return false;
      } finally {
        busyRef.current = false;
        setLive(null);
      }
    },
    [expert, history, setHistory]
  );

  function openCounter(message) {
    if (!expert) return;
    setOpen(true);
    if (message) sendMessage(message);
  }

  return (
    <div className="site">
      <SiteHeader expert={expert} onTalk={() => openCounter()} current={route.name} />
      <main>
        {loadError && (
          <div className="site-container load-error">
            We couldn't open the shop just now ({loadError}). Please refresh in a moment.
          </div>
        )}
        {route.name === "catalogue" && <CataloguePage search={location.search} />}
        {route.name === "stone" && <StonePage id={route.id} />}
        {route.name === "home" && (
          <>
            <Hero expert={expert} onAsk={openCounter} onTalk={() => openCounter()} />
            <MeetExpert expert={expert} onTalk={() => openCounter()} onAsk={openCounter} />
            <OnTheCounter stones={featured} />
            <HowItWorks />
            <ClosingCall onAsk={openCounter} />
          </>
        )}
      </main>
      <SiteFooter />

      {showFloat && !open && expert && (
        <button className="float-talk" onClick={() => openCounter()}>
          <span className="float-talk-dot" aria-hidden="true" />
          Talk to our {expert.display_name}
        </button>
      )}

      {open && expert && (
        <CounterView
          agent={expert}
          history={history}
          live={live}
          busy={Boolean(live)}
          error={error}
          restored={restored}
          onSend={sendMessage}
          onClose={() => setOpen(false)}
          onStartFresh={() => {
            setHistory([]);
            setRestored(false);
          }}
        />
      )}
    </div>
  );
}
