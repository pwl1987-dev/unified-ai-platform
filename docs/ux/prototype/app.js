(function () {
  var root = document.documentElement;
  var screens = Array.prototype.slice.call(document.querySelectorAll(".screen"));
  var navItems = Array.prototype.slice.call(document.querySelectorAll("[data-screen]"));
  var sidebarItems = Array.prototype.slice.call(document.querySelectorAll(".nav-item"));
  var toast = document.getElementById("toast");
  var themeIcon = document.getElementById("theme-icon");

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(function () {
      toast.classList.remove("show");
    }, 2200);
  }

  function activateScreen(name) {
    var target = document.getElementById("screen-" + name);
    if (!target) {
      return;
    }
    screens.forEach(function (screen) {
      screen.classList.toggle("active", screen === target);
    });
    sidebarItems.forEach(function (item) {
      item.classList.toggle("active", item.getAttribute("data-screen") === name);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
    document.title = target.getAttribute("data-title") + " · Unified AI Platform Prototype";
  }

  navItems.forEach(function (item) {
    item.addEventListener("click", function () {
      activateScreen(item.getAttribute("data-screen"));
    });
  });

  document.getElementById("operator-launch").addEventListener("click", function () {
    activateScreen("operator");
  });

  document.getElementById("theme-toggle").addEventListener("click", function () {
    var dark = root.getAttribute("data-theme") === "dark";
    root.setAttribute("data-theme", dark ? "light" : "dark");
    themeIcon.textContent = dark ? "◐" : "☼";
    showToast(dark ? "Switched to Light Mode" : "Switched to Dark Mode");
  });

  Array.prototype.slice.call(document.querySelectorAll("button")).forEach(function (button) {
    if (button.hasAttribute("data-screen") || button.id === "operator-launch" || button.id === "theme-toggle") {
      return;
    }
    button.addEventListener("click", function () {
      var label = button.textContent.trim().replace(/\s+/g, " ");
      if (label === "Approve" || label === "Reject") {
        showToast("Prototype only · Human decision was not executed");
      } else if (label.indexOf("Request approval") >= 0) {
        showToast("Prototype only · Approval request was not created");
      } else if (label.indexOf("Add candidate") >= 0) {
        showToast("Prototype only · No backend mutation");
      }
    });
  });
}());
