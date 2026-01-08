const fileInput = document.getElementById("csv-file");
const fileName = document.getElementById("file-name");
const form = document.querySelector("form");
const submitButton = document.querySelector(".button.primary");

if (fileInput && fileName) {
  fileInput.addEventListener("change", () => {
    const selected = fileInput.files && fileInput.files[0];
    fileName.textContent = selected ? selected.name : "No file selected";
  });
}

if (form && submitButton) {
  form.addEventListener("submit", () => {
    submitButton.disabled = true;
    submitButton.textContent = "Generating...";
  });
}
