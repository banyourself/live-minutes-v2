document.querySelectorAll("[data-menu]").forEach((button) => {
  button.addEventListener("click", async () => {
    const box = button.getBoundingClientRect();
    button.classList.add("open");
    await window.lm.showMenu(button.dataset.menu, box.left, box.bottom + 2);
    button.classList.remove("open");
  });
});
