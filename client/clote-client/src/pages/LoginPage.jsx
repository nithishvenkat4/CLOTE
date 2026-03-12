import { useState } from "react";
import { login } from "../services/authService";

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!username || !password) {
      setError("Please enter both username and password");
      return;
    }
    setLoading(true);
    setError("");
    const result = await login(username, password);
    setLoading(false);
    if (result.success) {
      onLogin();
    } else {
      setError(result.message || "Login failed. Check your credentials.");
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>CLOTE</h1>
        <p style={styles.subtitle}>Self-Hosted File Management</p>

        <input
          style={styles.input}
          type="text"
          placeholder="Username"
          value={username}
          onChange={e => setUsername(e.target.value)}
        />
        <input
          style={styles.input}
          type="password"
          placeholder="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleLogin()}
        />

        {error && <p style={styles.error}>{error}</p>}

        <button
          style={loading ? styles.buttonDisabled : styles.button}
          onClick={handleLogin}
          disabled={loading}
        >
          {loading ? "Connecting..." : "Login"}
        </button>
      </div>
    </div>
  );
}

const styles = {
  container: {
    height: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f0f4f8"
  },
  card: {
    backgroundColor: "#ffffff",
    padding: "40px",
    borderRadius: "12px",
    boxShadow: "0 4px 20px rgba(0,0,0,0.1)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    width: "320px"
  },
  title: {
    fontSize: "32px",
    fontWeight: "bold",
    color: "#1F4E79",
    margin: "0 0 4px 0"
  },
  subtitle: {
    fontSize: "13px",
    color: "#888",
    marginBottom: "28px"
  },
  input: {
    width: "100%",
    padding: "12px",
    marginBottom: "12px",
    borderRadius: "8px",
    border: "1px solid #ccc",
    fontSize: "14px",
    outline: "none",
    boxSizing: "border-box"
  },
  button: {
    width: "100%",
    padding: "12px",
    backgroundColor: "#1F4E79",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "15px",
    fontWeight: "bold",
    cursor: "pointer",
    marginTop: "8px"
  },
  buttonDisabled: {
    width: "100%",
    padding: "12px",
    backgroundColor: "#aaa",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "15px",
    cursor: "not-allowed",
    marginTop: "8px"
  },
  error: {
    color: "#e74c3c",
    fontSize: "13px",
    marginBottom: "8px",
    textAlign: "center"
  }
};