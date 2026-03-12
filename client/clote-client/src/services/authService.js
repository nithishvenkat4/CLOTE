import API_BASE from "./api";

export const login = async(username, password) => {
    try {
        const formData = new URLSearchParams();
        formData.append("username", username);
        formData.append("password", password);

        const response = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            localStorage.setItem("token", data.access_token);
            return { success: true };
        }

        if (data.detail) {
            if (typeof data.detail === "string") {
                return { success: false, message: data.detail };
            }
            if (Array.isArray(data.detail)) {
                return { success: false, message: (data.detail[0] && data.detail[0].msg) || "Invalid input" };
            }
        }

        return { success: false, message: "Login failed" };

    } catch (err) {
        return { success: false, message: "Cannot reach server. Check connection." };
    }
};

export const logout = () => {
    localStorage.removeItem("token");
};

export const isLoggedIn = () => {
    return !!localStorage.getItem("token");
};