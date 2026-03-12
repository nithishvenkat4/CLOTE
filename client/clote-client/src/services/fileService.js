import API_BASE, { getHeaders } from "./api";

export const getFiles = async () => {
  const response = await fetch(`${API_BASE}/files`, {
    headers: getHeaders()
  });
  return response.json();
};

export const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/files/upload`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${localStorage.getItem("token")}`
    },
    body: formData
  });
  return response.json();
};

export const downloadFile = async (fileId, filename) => {
  const response = await fetch(`${API_BASE}/files/${fileId}/download`, {
    headers: getHeaders()
  });
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
};

export const getVersions = async (fileId) => {
  const response = await fetch(`${API_BASE}/files/${fileId}/versions`, {
    headers: getHeaders()
  });
  return response.json();
};

export const rollbackVersion = async (fileId, versionNumber) => {
  const response = await fetch(`${API_BASE}/files/${fileId}/rollback/${versionNumber}`, {
    method: "POST",
    headers: getHeaders()
  });
  return response.json();
};