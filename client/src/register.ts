import { authenticate, AuthFailure, createAccount } from "./auth";
import { prepareGame } from "./game/main";

export async function registerPageHandler() {
    const userField = document.getElementById('user-field') as HTMLInputElement;
    const passwordField = document.getElementById('password-field') as HTMLInputElement;

    document.getElementById('register-form')!.addEventListener('submit', async (event) => {
        event.preventDefault();

        const result = await createAccount(userField.value, passwordField.value);
        if (result instanceof AuthFailure) {
            alert('Registration failed: ' + result.reason);
        } else {
            // Seems successful, let's try logging in
            await authenticate(userField.value, passwordField.value);
            await prepareGame();
        }
    });
}