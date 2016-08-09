var Search = React.createClass({
  render: function() {
    return (
      <div className="search item">
        <a href={"/summary/" + this.props.date_path}>
          {this.props.text}
        </a>
        &nbsp;[
        <a href={"https://twitter.com/" + this.props.twitter_user}>
          {this.props.twitter_user}
        </a>]
        &nbsp;({this.props.status})
      </div>
    );
  }
});

var SearchList = React.createClass({
  render: function() {
    var searchNodes = this.props.data.map(function(search) {
      return (
        <Search text={search.text}
          key={search.id}
          id={search.id}
          date_path={search.date_path}
          status={search.status}
          twitter_user={search.twitter_user}>

        </Search>
      );
    });
    return (
      <div className="searchList">
        {searchNodes}
      </div>
    );
  }
});

var SearchForm = React.createClass({
  getInitialState: function() {
    return {text: '', count: '1000'};
  },
  handleTextChange: function(e) {
    this.setState({text: e.target.value});
  },
  handleCountChange: function(e) {
    this.setState({count: e.target.value});
  },
  handleSubmit: function(e) {
    e.preventDefault();
    var text = this.state.text.trim();
    var count = this.state.count.trim();
    if (!text || !count) {
      return;
    }
    this.props.onSearchSubmit({text: text, count: count});
    this.setState({text: '', count: '1000'});
  },
  render: function() {
    return (
      <form className="searchForm" onSubmit={this.handleSubmit}>
        terms: <input type='text'
          value={this.state.text}
          onChange={this.handleTextChange} />
        count: <input type='text'
          value={this.state.count}
          onChange={this.handleCountChange} />
        <input type='submit' value='add' />
      </form>
    );
  }
});

var SearchBox = React.createClass({
  loadSearchesFromServer: function() {
    $.ajax({
      url: this.props.url,
      dataType: 'json',
      cache: false,
      success: function(data) {
        this.setState({data: data});
      }.bind(this),
      error: function(xhr, status, err) {
        console.error(this.props.url, status, err.toString());
      }.bind(this)
    });
  },
  handleSearchSubmit: function(search) {
    $.ajax({
      // url: this.props.url,
      url: '/searches/',
      dataType: 'json',
      type: 'POST',
      data: search,
      success: function(data) {
        this.setState({data: data});
      }.bind(this),
      error: function(xhr, status, err) {
        this.setState({error: xhr.responseJSON.error});
        console.error(this.props.url, status, err.toString());
      }.bind(this)
    });
  },
  getInitialState: function() {
    return {data: []};
  },
  componentDidMount: function() {
    this.loadSearchesFromServer();
    setInterval(this.loadSearchesFromServer, this.props.pollInterval);
  },
  render: function() {
    return (
      <div className="searchBox">
        <h1>hi there</h1>
        <h2>search something new</h2>
        <h3 style={{color: 'red'}}>{ this.state.error }</h3>
        <SearchForm onSearchSubmit={this.handleSearchSubmit} />
        <SearchList data={this.state.data} />
      </div>
    );
  }
});


ReactDOM.render(
  <SearchBox url="/api/searches/" pollInterval={2000} />,
  document.getElementById('content')
);
