import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { FluentProvider, webDarkTheme } from "@fluentui/react-components";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <FluentProvider theme={webDarkTheme} className="app-provider">
      <App />
    </FluentProvider>
  </StrictMode>
);
