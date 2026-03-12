import { useState } from "react";
import { isLoggedIn } from "./services/authService";
import LoginPage from "./pages/LoginPage";
import FileBrowserPage from "./pages/FileBrowserPage";

export default function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());

  return loggedIn
    ? <FileBrowserPage onLogout={() => setLoggedIn(false)} />
    : <LoginPage onLogin={() => setLoggedIn(true)} />;
}