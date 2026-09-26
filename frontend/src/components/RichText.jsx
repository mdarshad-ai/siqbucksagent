// Dealers sometimes use light markdown. Render **bold** and *italic* as real
// emphasis (as React text, never HTML) instead of showing the asterisks.
const PATTERN = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g;

export default function RichText({ text }) {
  return (text || "").split(PATTERN).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}
