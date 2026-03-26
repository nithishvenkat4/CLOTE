const BASE = "http://10.252.41.216:8000";

function getToken() {
    return localStorage.getItem("clote_token");
}

function authHeaders(extra = {}) {
    return {
        Authorization: `Bearer ${getToken()}`,
        ...extra,
    };
}

async function handleResponse(res) {
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Request failed");
    }
    return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function register(username, password) {
    return handleResponse(
        await fetch(`${BASE}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        })
    );
}

export async function login(username, password) {
    return handleResponse(
        await fetch(`${BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        })
    );
}

// ── Files ─────────────────────────────────────────────────────────────────────

export async function listFiles() {
    return handleResponse(
        await fetch(`${BASE}/files/`, { headers: authHeaders() })
    );
}

export async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file);
    return handleResponse(
        await fetch(`${BASE}/files/upload`, {
            method: "POST",
            headers: authHeaders(),
            body: fd,
        })
    );
}

export async function downloadFile(fileId, filename) {
    const res = await fetch(`${BASE}/files/${fileId}/download`, {
        headers: authHeaders(),
    });
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

export async function deleteFile(fileId) {
    return handleResponse(
        await fetch(`${BASE}/files/${fileId}`, {
            method: "DELETE",
            headers: authHeaders(),
        })
    );
}

export async function renameFile(fileId, filename) {
    return handleResponse(
        await fetch(`${BASE}/files/${fileId}/rename`, {
            method: "PATCH",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ filename }),
        })
    );
}

export async function moveFile(fileId, folderId) {
    return handleResponse(
        await fetch(`${BASE}/files/${fileId}/move`, {
            method: "PATCH",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ folder_id: folderId }),
        })
    );
}

// ── Versions ──────────────────────────────────────────────────────────────────

export async function listVersions(fileId) {
    return handleResponse(
        await fetch(`${BASE}/files/${fileId}/versions`, { headers: authHeaders() })
    );
}

export async function uploadVersion(fileId, file, note = "") {
    const fd = new FormData();
    fd.append("file", file);
    if (note) fd.append("note", note);
    return handleResponse(
        await fetch(`${BASE}/files/${fileId}/upload`, {
            method: "POST",
            headers: authHeaders(),
            body: fd,
        })
    );
}

export async function downloadVersion(fileId, versionNum, filename) {
    const res = await fetch(
        `${BASE}/files/${fileId}/versions/${versionNum}/download`, { headers: authHeaders() }
    );
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename}_v${versionNum}`;
    a.click();
    URL.revokeObjectURL(url);
}

export async function deleteVersion(fileId, versionNum) {
    return handleResponse(
        await fetch(`${BASE}/files/${fileId}/versions/${versionNum}`, {
            method: "DELETE",
            headers: authHeaders(),
        })
    );
}

// ── Folders ───────────────────────────────────────────────────────────────────

export async function listRootFolders() {
    return handleResponse(
        await fetch(`${BASE}/folders/`, { headers: authHeaders() })
    );
}

export async function createFolder(name, parentId = null) {
    return handleResponse(
        await fetch(`${BASE}/folders/`, {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ name, parent_id: parentId }),
        })
    );
}

export async function getFolderContents(folderId) {
    return handleResponse(
        await fetch(`${BASE}/folders/${folderId}`, { headers: authHeaders() })
    );
}

export async function uploadToFolder(folderId, files) {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return handleResponse(
        await fetch(`${BASE}/folders/${folderId}/upload`, {
            method: "POST",
            headers: authHeaders(),
            body: fd,
        })
    );
}

export async function renameFolder(folderId, name) {
    return handleResponse(
        await fetch(`${BASE}/folders/${folderId}/rename`, {
            method: "PATCH",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ name }),
        })
    );
}

export async function deleteFolder(folderId) {
    return handleResponse(
        await fetch(`${BASE}/folders/${folderId}`, {
            method: "DELETE",
            headers: authHeaders(),
        })
    );
}