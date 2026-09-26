// Homepage copy for each partner. Personas themselves are edited in /admin;
// this is just the shop-window text. Unknown partners get the fallback.
export const PARTNER_COPY = {
  siq: {
    role: "The fine-stone specialist",
    knownFor: ["Certified fine gemstones", "One trusted source", "Provenance you can trace"],
    questions: ["What's your rarest stone?", "Anything certified and unheated?", "Help me pick an engagement stone"],
    greeting: "Looking for something truly special tonight?",
  },
  bucks: {
    role: "The dealer who knows what's moving",
    knownFor: ["Great finds at fair prices", "Stones from everywhere", "Can source what you're after"],
    questions: ["Best deal you've got today?", "A gift under $50?", "Got any crystals for my shelf?"],
    greeting: "Whatever you're after, I've probably got a line on it.",
  },
};

const FALLBACK = {
  role: "Gem partner",
  knownFor: [],
  questions: ["What would you recommend?", "What's new in?"],
  greeting: "Ask me anything about the stones.",
};

export function partnerCopy(agentId) {
  return PARTNER_COPY[agentId] || FALLBACK;
}

export const HERO_PROMPTS = [
  "Something rare and certified",
  "A gift under $100",
  "A blue stone under $2,000",
];
