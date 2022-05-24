const css = `
.bk.debugger-card {
  border: 1px solid rgba(0,0,0,1);
  color: rgba(255,255,255,1);
  background-color: rgba(0,0,0,1);
  border-radius: 0rem;
}
.bk.debugger-card-header {
  align-items: center;
  text-align: left;
  background-color: rgba(0, 0, 0, 1)!important;
  color: rgba(255, 255, 255, 1);
  border-radius: 0rem;
  display: inline-flex;
  justify-content: start;
  width: 100%;
}
.bk.debugger-card-button {
  background-color: transparent;
  color: rgba(255, 255, 255, 1);
  margin-left: 0.5em;
}
.bk.debugger-card-title {
  align-items: center;
  text-align: left;
  color: rgba(255, 255, 255, 1);
  font-size: 1em;
  overflow-wrap: break-word;
}

/* Special debugger buttons for clearing and saving */
.bk button.special_btn {
    width: 25px;
    height: 25px;
    background-color: black;
    color: white;
    display: inline-block;
}


.bk button.special_btn .tooltiptext {
  visibility: hidden;
  width: 100px;
  background-color: darkgray;
  color: #fff;
  text-align: center;
  border-radius: 6px;
  padding: 5px 0;

  /* Position the tooltip */
  position: relative;
  z-index: 1;
  top: 100%;
  left: 100%;
  margin-left: -100px;
  display: block;
}

.bk button.special_btn:hover .tooltiptext {
  visibility: visible;
}



.bk button.clear_btn:hover .shown { display: none;}
.bk button.clear_btn:hover:before { content: "☑"; }
`;
export default css;
