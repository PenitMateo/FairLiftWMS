function login() {
    let username = document.getElementById("username").value;
    let password = document.getElementById("password").value;
    let message = document.getElementById("message");

    // Hardcoded credentials (for demo purposes)
    const validUsername = "00001";
    const validPassword = "password123";

    if (username === validUsername && password === validPassword) {
        message.style.color = "green";
        message.textContent = "Login successful!";
        setTimeout(() => {
            window.location.href = "dashboard.html"; // Redirect to another page
        }, 1000);
    } else {
        message.style.color = "red";
        message.textContent = "Invalid userid or password.";
    }
}
