import { useState, useEffect } from "react";
import { getFiles } from "../services/fileService";
import { logout } from "../services/authService";

export default function FileBrowserPage({ onLogout }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [serverStatus, setServerStatus] = useState("checking");

  useEffect(() => {
    checkServerAndLoad();
  }, []);

  const checkServerAndLoad = async () => {
    try {
      const res = await fetch("http://10.252.41.216:8000/health");
      if (res.ok) {
        setServerStatus("online");
        loadFiles();
      } else {
        setServerStatus("offline");
        setLoading(false);
      }
    } catch {
      setServerStatus("offline");
      setLoading(false);
    }
  };

  const loadFiles = async () => {
    try {
      const data = await getFiles();
      setFiles(Array.isArray(data) ? data : data.files || []);
    } catch {
      setError("Could not load files.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    onLogout();
  };

  return (
    <div style={styles.container}>

      {/* Top Bar */}
      <div style={styles.topbar}>
        <h2 style={styles.logo}>CLOTE</h2>
        <div style={styles.statusRow}>
          <div style={{
            ...styles.statusDot,
            backgroundColor: serverStatus === "online" ? "#2ecc71" : "#e74c3c"
          }} />
          <span style={styles.statusText}>
            {serverStatus === "online" ? "Server Online" : "Server Offline"}
          </span>
        </div>
        <button style={styles.logoutBtn} onClick={handleLogout}>Logout</button>
      </div>

      {/* Main Content */}
      <div style={styles.content}>
        {loading && <p style={styles.info}>Loading files...</p>}
        {error && <p style={styles.error}>{error}</p>}
        {!loading && serverStatus === "offline" && (
          <div style={styles.offlineBox}>
            <p>⚠️ Server is currently offline.</p>
            <p>Files will load automatically when Person A's server starts.</p>
            <button style={styles.retryBtn} onClick={checkServerAndLoad}>
              Retry Now
            </button>
          </div>
        )}
        {!loading && serverStatus === "online" && files.length === 0 && (
          <p style={styles.info}>No files uploaded yet.</p>
        )}
        {files.map(file => (
          <div key={file.id} style={styles.fileCard}>
            <span style={styles.fileName}>{file.filename || file.name || "Unnamed"}</span>
            <span style={styles.fileSize}>{(file.size_bytes / 1024).toFixed(1)} KB</span>
          </div>
        ))}
      </div>

    </div>
  );
}

const styles = {
  container: { minHeight: "100vh", backgroundColor: "#f0f4f8", fontFamily: "Arial" },
  topbar: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    backgroundColor: "#1F4E79", padding: "16px 32px"
  },
  logo: { color: "#fff", margin: 0, fontSize: "22px" },
  statusRow: { display: "flex", alignItems: "center", gap: "8px" },
  statusDot: { width: "10px", height: "10px", borderRadius: "50%" },
  statusText: { color: "#fff", fontSize: "13px" },
  logoutBtn: {
    backgroundColor: "transparent", border: "1px solid #fff",
    color: "#fff", padding: "6px 16px", borderRadius: "6px", cursor: "pointer"
  },
  content: { padding: "32px" },
  fileCard: {
    backgroundColor: "#fff", padding: "16px 20px", borderRadius: "8px",
    marginBottom: "10px", display: "flex", justifyContent: "space-between",
    boxShadow: "0 2px 6px rgba(0,0,0,0.06)"
  },
  fileName: { fontWeight: "bold", color: "#1F4E79" },
  fileSize: { color: "#888", fontSize: "13px" },
  info: { color: "#888", textAlign: "center", marginTop: "60px" },
  error: { color: "#e74c3c", textAlign: "center" },
  offlineBox: {
    textAlign: "center", marginTop: "60px", color: "#555",
    backgroundColor: "#fff", padding: "40px", borderRadius: "12px",
    boxShadow: "0 2px 10px rgba(219, 199, 199, 0.08)"
  },
  retryBtn: {
    marginTop: "16px", padding: "10px 24px", backgroundColor: "#1F4E79",
    color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer"
  }
};