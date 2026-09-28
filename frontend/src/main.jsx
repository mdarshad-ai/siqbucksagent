import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import AdminApp from "./admin/AdminApp.jsx";
import "./styles/base.css";
import "./styles/character.css";
import "./styles/cards.css";
import "./styles/site.css";
import "./styles/counter.css";
import "./styles/catalogue.css";

const isAdmin = window.location.pathname.replace(/\/+$/, "").startsWith("/admin");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>{isAdmin ? <AdminApp /> : <App />}</React.StrictMode>
);
