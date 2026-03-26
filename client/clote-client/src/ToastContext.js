import { createContext, useContext, useState, useCallback } from "react";

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    const toast = useCallback((msg, type = "info") => {
        const id = Date.now();
        setToasts((t) => [...t, { id, msg, type }]);
        setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
    }, []);

    const icons = { success: "✓", error: "✕", info: "ℹ" };

    return ( <
        ToastContext.Provider value = { toast } > { children } <
        div className = "toast-container" > {
            toasts.map((t) => ( <
                div key = { t.id }
                className = { `toast ${t.type}` } >
                <
                span > { icons[t.type] } < /span> <
                span > { t.msg } < /span> <
                /div>
            ))
        } <
        /div> <
        /ToastContext.Provider>
    );
}

export function useToast() {
    return useContext(ToastContext);
}