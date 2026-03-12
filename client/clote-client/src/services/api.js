const API_BASE = "http://10.252.41.216:8000";

export const getHeaders = () => ({
  "Authorization": `Bearer ${localStorage.getItem("token")}`,
  "Content-Type": "application/json"
});

export default API_BASE;