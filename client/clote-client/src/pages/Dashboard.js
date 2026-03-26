import { useState, useEffect, useCallback, useRef } from "react";
import {
    listFiles,
    uploadFile,
    downloadFile,
    deleteFile,
    renameFile,
    moveFile,
    getFolderContents,
    uploadToFolder,
    deleteFolder,
    renameFolder,
    listRootFolders,
    createFolder,
} from "../api/client";
import { useAuth } from "../AuthContext";
import { useToast } from "../ToastContext";
import Sidebar from "../components/Sidebar";
import VersionModal from "../components/VersionModal";
import "./Dashboard.css";

function formatBytes(b) {
    if (!b) return "—";
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(iso) {
    return new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function getExt(filename) {
    const parts = filename.split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

function FileIcon({ filename }) {
    const ext = getExt(filename);
    const map = {
        pdf: { icon: "📄", color: "#f85149" },
        png: { icon: "🖼", color: "#58a6ff" },
        jpg: { icon: "🖼", color: "#58a6ff" },
        jpeg: { icon: "🖼", color: "#58a6ff" },
        mp4: { icon: "🎬", color: "#bc8cff" },
        mp3: { icon: "🎵", color: "#bc8cff" },
        zip: { icon: "📦", color: "#d29922" },
        txt: { icon: "📝", color: "#8b949e" },
        js: { icon: "⟨/⟩", color: "#f7c948" },
        py: { icon: "🐍", color: "#3fb950" },
        md: { icon: "Ⅿ", color: "#58a6ff" },
    };
    const { icon, color } = map[ext] || { icon: "📁", color: "#8b949e" };
    return <span className = "file-icon"
    style = {
        { color } } > { icon } < /span>;
}

// Context menu
function CtxMenu({ x, y, items, onClose }) {
    const ref = useRef();
    useEffect(() => {
        function handler(e) {
            if (ref.current && !ref.current.contains(e.target)) onClose();
        }
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [onClose]);

    return ( <
        div className = "ctx-menu"
        ref = { ref }
        style = {
            { left: x, top: y } } > {
            items.map((item, i) =>
                item === "---" ? ( <
                    div key = { i }
                    className = "ctx-divider" / >
                ) : ( <
                    div key = { i }
                    className = { `ctx-item ${item.danger ? "danger" : ""}` }
                    onClick = {
                        () => { item.action();
                            onClose(); } } >
                    <
                    span > { item.icon } < /span> <
                    span > { item.label } < /span> <
                    /div>
                )
            )
        } <
        /div>
    );
}

// Rename inline modal
function RenameModal({ current, onConfirm, onClose }) {
    const [value, setValue] = useState(current);
    return ( <
        div className = "modal-backdrop"
        onClick = {
            (e) => e.target === e.currentTarget && onClose() } >
        <
        div className = "modal" >
        <
        div className = "modal-title" > Rename < /div> <
        input autoFocus value = { value }
        onChange = {
            (e) => setValue(e.target.value) }
        onKeyDown = {
            (e) => e.key === "Enter" && onConfirm(value) }
        /> <
        div className = "modal-actions" >
        <
        button className = "btn btn-ghost"
        onClick = { onClose } > Cancel < /button> <
        button className = "btn btn-primary"
        onClick = {
            () => onConfirm(value) } > Rename < /button> <
        /div> <
        /div> <
        /div>
    );
}

export default function Dashboard() {
    const { username, logout } = useAuth();
    const toast = useToast();

    const [selectedFolder, setSelectedFolder] = useState(null); // null = root
    const [files, setFiles] = useState([]);
    const [subfolders, setSubfolders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);

    const [ctx, setCtx] = useState(null); // { x, y, items }
    const [versionFile, setVersionFile] = useState(null);
    const [renameTarget, setRenameTarget] = useState(null); // { type: 'file'|'folder', item }

    const [search, setSearch] = useState("");
    const [newFolderName, setNewFolderName] = useState("");
    const [showNewFolder, setShowNewFolder] = useState(false);

    const load = useCallback(async() => {
        setLoading(true);
        try {
            if (!selectedFolder) {
                const [f] = await Promise.all([listFiles()]);
                setFiles(f);
                const folders = await listRootFolders();
                setSubfolders(folders);
            } else {
                const data = await getFolderContents(selectedFolder.id);
                setFiles(data.files || []);
                setSubfolders(data.subfolders || []);
            }
        } catch (err) {
            toast(err.message, "error");
        } finally {
            setLoading(false);
        }
    }, [selectedFolder, toast]);

    useEffect(() => { load(); }, [load]);

    // ── Upload ─────────────────────────────────────────────────────────────────

    async function handleUpload(e) {
        const picked = Array.from(e.target.files);
        if (!picked.length) return;
        setUploading(true);
        try {
            if (selectedFolder) {
                await uploadToFolder(selectedFolder.id, picked);
                toast(`${picked.length} file(s) uploaded to ${selectedFolder.name}`, "success");
            } else {
                await Promise.all(picked.map((f) => uploadFile(f)));
                toast(`${picked.length} file(s) uploaded`, "success");
            }
            load();
        } catch (err) {
            toast(err.message, "error");
        } finally {
            setUploading(false);
            e.target.value = "";
        }
    }

    // ── File actions ───────────────────────────────────────────────────────────

    function openFileCtx(e, file) {
        e.preventDefault();
        setCtx({
            x: e.clientX,
            y: e.clientY,
            items: [
                { icon: "↓", label: "Download", action: () => downloadFile(file.id, file.filename) },
                { icon: "⏱", label: "Version history", action: () => setVersionFile(file) },
                { icon: "✎", label: "Rename", action: () => setRenameTarget({ type: "file", item: file }) },
                "---",
                { icon: "✕", label: "Delete", danger: true, action: () => handleDeleteFile(file) },
            ],
        });
    }

    async function handleDeleteFile(file) {
        try {
            await deleteFile(file.id);
            toast(`${file.filename} deleted`, "success");
            load();
        } catch (err) { toast(err.message, "error"); }
    }

    async function handleRenameFile(newName) {
        try {
            await renameFile(renameTarget.item.id, newName);
            toast("Renamed", "success");
            setRenameTarget(null);
            load();
        } catch (err) { toast(err.message, "error"); }
    }

    // ── Folder actions ─────────────────────────────────────────────────────────

    function openFolderCtx(e, folder) {
        e.preventDefault();
        setCtx({
            x: e.clientX,
            y: e.clientY,
            items: [
                { icon: "↳", label: "Open", action: () => setSelectedFolder(folder) },
                { icon: "✎", label: "Rename", action: () => setRenameTarget({ type: "folder", item: folder }) },
                "---",
                { icon: "✕", label: "Delete folder", danger: true, action: () => handleDeleteFolder(folder) },
            ],
        });
    }

    async function handleDeleteFolder(folder) {
        try {
            await deleteFolder(folder.id);
            toast(`${folder.name} deleted`, "success");
            if (selectedFolder ? .id === folder.id) setSelectedFolder(null);
            load();
        } catch (err) { toast(err.message, "error"); }
    }

    async function handleRenameFolder(newName) {
        try {
            await renameFolder(renameTarget.item.id, newName);
            toast("Renamed", "success");
            setRenameTarget(null);
            load();
        } catch (err) { toast(err.message, "error"); }
    }

    async function handleCreateFolder(e) {
        e.preventDefault();
        if (!newFolderName.trim()) return;
        try {
            await createFolder(newFolderName.trim(), selectedFolder ? .id ? ? null);
            toast("Folder created", "success");
            setNewFolderName("");
            setShowNewFolder(false);
            load();
        } catch (err) { toast(err.message, "error"); }
    }

    // ── Filter ─────────────────────────────────────────────────────────────────

    const filteredFiles = files.filter((f) =>
        f.filename.toLowerCase().includes(search.toLowerCase())
    );
    const filteredFolders = subfolders.filter((f) =>
        f.name.toLowerCase().includes(search.toLowerCase())
    );

    const breadcrumb = selectedFolder ? selectedFolder.name : "Root";

    return ( <
        div className = "dash-root" > { /* Topbar */ } <
        header className = "topbar" >
        <
        div className = "topbar-left" >
        <
        span className = "topbar-logo" > ⬡CLOTE < /span> <
        span className = "topbar-sep" > /</span >
        <
        span className = "topbar-breadcrumb" > { breadcrumb } < /span> <
        /div> <
        div className = "topbar-right" >
        <
        span className = "topbar-user mono" > @ { username } < /span> <
        button className = "btn btn-ghost"
        onClick = { logout } > Sign out < /button> <
        /div> <
        /header>

        <
        div className = "dash-body" > { /* Sidebar */ } <
        Sidebar selectedFolder = { selectedFolder }
        onSelectFolder = { setSelectedFolder }
        onSelectRoot = {
            () => setSelectedFolder(null) }
        />

        { /* Main */ } <
        main className = "main-area" > { /* Toolbar */ } <
        div className = "toolbar" >
        <
        div className = "toolbar-left" >
        <
        input className = "search-input"
        placeholder = "Search files…"
        value = { search }
        onChange = {
            (e) => setSearch(e.target.value) }
        /> <
        /div> <
        div className = "toolbar-right" >
        <
        button className = "btn btn-ghost"
        onClick = {
            () => setShowNewFolder((s) => !s) } >
        +Folder < /button>

        <
        label className = "btn btn-primary"
        style = {
            { cursor: "pointer" } } > { uploading ? "Uploading…" : "↑ Upload" } <
        input type = "file"
        multiple className = "sr-only"
        onChange = { handleUpload }
        disabled = { uploading }
        /> <
        /label> <
        /div> <
        /div>

        { /* New folder inline */ } {
            showNewFolder && ( <
                form className = "new-folder-bar"
                onSubmit = { handleCreateFolder } >
                <
                input autoFocus placeholder = "New folder name"
                value = { newFolderName }
                onChange = {
                    (e) => setNewFolderName(e.target.value) }
                onKeyDown = {
                    (e) => e.key === "Escape" && setShowNewFolder(false) }
                /> <
                button className = "btn btn-primary"
                type = "submit" > Create < /button> <
                button className = "btn btn-ghost"
                type = "button"
                onClick = {
                    () => setShowNewFolder(false) } > Cancel < /button> <
                /form>
            )
        }

        { /* Content */ } {
            loading ? ( <
                div className = "main-empty" >
                <
                div className = "spinner" / >
                <
                /div>
            ) : ( <
                div className = "file-grid" > { /* Subfolders */ } {
                    filteredFolders.map((folder) => ( <
                        div key = { `folder-${folder.id}` }
                        className = "file-card folder-card"
                        onDoubleClick = {
                            () => setSelectedFolder(folder) }
                        onContextMenu = {
                            (e) => openFolderCtx(e, folder) } >
                        <
                        div className = "file-card-icon" > ⬡ < /div> <
                        div className = "file-card-name truncate" > { folder.name } < /div> <
                        div className = "file-card-meta" > Folder < /div> <
                        /div>
                    ))
                }

                { /* Files */ } {
                    filteredFiles.map((file) => ( <
                        div key = { `file-${file.id}` }
                        className = "file-card"
                        onContextMenu = {
                            (e) => openFileCtx(e, file) }
                        onDoubleClick = {
                            () => downloadFile(file.id, file.filename) } >
                        <
                        div className = "file-card-icon" >
                        <
                        FileIcon filename = { file.filename }
                        /> <
                        /div> <
                        div className = "file-card-name truncate" > { file.filename } < /div> <
                        div className = "file-card-meta" >
                        <
                        span > { formatBytes(file.size_bytes) } < /span> <
                        span className = "tag tag-blue" > v { file.current_version } < /span> <
                        /div> <
                        div className = "file-card-date" > { formatDate(file.updated_at) } < /div> <
                        /div>
                    ))
                }

                {
                    filteredFolders.length === 0 && filteredFiles.length === 0 && ( <
                        div className = "main-empty-state" >
                        <
                        span className = "empty-icon" > ⬡ < /span> <
                        p > Empty { selectedFolder ? `— ${selectedFolder.name}` : "root" } < /p> <
                        p className = "empty-hint" > Upload files or create a folder to get started < /p> <
                        /div>
                    )
                } <
                /div>
            )
        } <
        /main> <
        /div>

        { /* Context menu */ } {
            ctx && ( <
                CtxMenu x = { ctx.x }
                y = { ctx.y }
                items = { ctx.items }
                onClose = {
                    () => setCtx(null) }
                />
            )
        }

        { /* Version modal */ } {
            versionFile && ( <
                VersionModal file = { versionFile }
                onClose = {
                    () => setVersionFile(null) }
                onRefresh = { load }
                />
            )
        }

        { /* Rename modal */ } {
            renameTarget && ( <
                RenameModal current = { renameTarget.type === "file" ? renameTarget.item.filename : renameTarget.item.name }
                onConfirm = { renameTarget.type === "file" ? handleRenameFile : handleRenameFolder }
                onClose = {
                    () => setRenameTarget(null) }
                />
            )
        } <
        /div>
    );
}