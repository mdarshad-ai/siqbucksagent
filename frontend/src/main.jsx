import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import AdminApp from "./admin/AdminApp.jsx";
import "./App.css";

const isAdmin = window.location.pathname.replace(/\/+$/, "").startsWith("/admin");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>{isAdmin ? <AdminApp /> : <App />}</React.StrictMode>
);
