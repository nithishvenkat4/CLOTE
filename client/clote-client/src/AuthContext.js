import { createContext, useContext, useState, useCallback } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [token, setToken] = useState(() => localStorage.getItem("clote_token"));
    const [username, setUsername] = useState(() => localStorage.getItem("clote_user"));

    const saveAuth = useCallback((token, username) => {
        localStorage.setItem("clote_token", token);
        localStorage.setItem("clote_user", username);
        setToken(token);
        setUsername(username);
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem("clote_token");
        localStorage.removeItem("clote_user");
        setToken(null);
        setUsername(null);
    }, []);

    return ( <
        AuthContext.Provider value = {
            { token, username, saveAuth, logout, isAuthed: !!token } } > { children } <
        /AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}