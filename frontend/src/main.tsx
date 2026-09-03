import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import CredentialsPage from "./auth/CredentialsPage";
import RequireSession from "./auth/RequireSession";
import { SessionProvider } from "./auth/SessionProvider";
import { apply, readChoice } from "./theme";
import "./styles.css";

// Resolve the stored theme before the first render: the strict CSP forbids the
// usual inline pre-paint script, so this module is the earliest hook available.
apply(readChoice());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <Routes>
          {/* Open to anyone (T07-C03). */}
          <Route path="/login" element={<CredentialsPage mode="login" />} />
          <Route path="/signup" element={<CredentialsPage mode="signup" />} />
          {/* Gated (T07-C97). */}
          <Route
            path="/app"
            element={
              <RequireSession>
                <App />
              </RequireSession>
            }
          />
          {/* `/` decides by session: the gate sends a stranger to /login and
              lets a signed-in user through, so one redirect covers both. */}
          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
